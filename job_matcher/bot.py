from __future__ import annotations

import asyncio
import html
import json
from pathlib import Path
from queue import Empty
from typing import Optional
from urllib.parse import urlencode

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Settings, load_settings
from .freelancer_api_helper import FreelancerJob, create_bid
from .job_matcher_service import JobMatcherService
from .job_state_store import JobStateStore
from .open_ai_api_helper import generate_cover_letter
from .profile_store import ProfileStore


class JobMatcherBot:
    def __init__(
        self,
        settings: Settings,
        profile_store: ProfileStore,
        job_state_store: JobStateStore,
        matcher_service: JobMatcherService,
    ):
        self.settings = settings
        self.profile_store = profile_store
        self.job_state_store = job_state_store
        self.matcher_service = matcher_service
        self.application = Application.builder().token(settings.telegram.bot_token).build()

    def setup_handlers(self) -> None:
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        self.application.add_handler(
            MessageHandler(filters.StatusUpdate.WEB_APP_DATA, self.handle_webapp_submission)
        )
        self.application.job_queue.run_repeating(self._drain_job_queue, interval=5, first=5)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_main_menu(update, context)

    async def _send_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        profile = self.profile_store.get_profile(user_id)
        has_profile = profile is not None

        inline_buttons = [
            [
                InlineKeyboardButton(
                    "▶️ Start job matching", callback_data="action:start"
                ),
                InlineKeyboardButton(
                    "⏹ Stop job matching", callback_data="action:stop"
                ),
            ],
            [
                InlineKeyboardButton("View profile", callback_data="action:view"),
            ],
        ]
        reply_keyboard = ReplyKeyboardMarkup(
            [
                [
                    KeyboardButton(
                        text="Create Profile" if not has_profile else "Edit Profile",
                        web_app=WebAppInfo(url=self.settings.webapp.profile_form_url),
                    )
                ]
            ],
            resize_keyboard=True,
        )
        greeting = (
            "Welcome to Job Matcher!\n"
            "• Use the button below to open the mini app and edit your profile.\n"
            "• Tap Start job matching when you are ready to receive leads."
        )
        if update.message:
            await update.message.reply_text(
                greeting,
                reply_markup=reply_keyboard,
            )
            await update.message.reply_text(
                "Control panel:",
                reply_markup=InlineKeyboardMarkup(inline_buttons),
            )
        elif update.callback_query:
            await update.callback_query.message.edit_text(
                greeting,
                reply_markup=InlineKeyboardMarkup(inline_buttons),
                parse_mode=ParseMode.MARKDOWN,
            )

    async def handle_webapp_submission(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        data_raw = update.effective_message.web_app_data.data
        try:
            payload = json.loads(data_raw)
        except json.JSONDecodeError:
            await update.effective_message.reply_text("Unable to parse form submission.")
            return

        form_type = payload.get("form_type", "profile")
        form_data = payload.get("data", payload)

        if form_type == "profile":
            form_data["telegram_user_id"] = user_id
            self.profile_store.upsert_profile(user_id, form_data)
            await update.effective_message.reply_text("Profile saved successfully ✅")
            return

        if form_type == "bid":
            await self._process_bid_form_submission(update, user_id, form_data)
            return

        await update.effective_message.reply_text("Unknown form submission received.")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        data = query.data or ""
        if data.startswith("action:"):
            action = data.split(":")[1]
            if action == "start":
                self.matcher_service.enable_user(query.from_user.id)
                await query.edit_message_text("Job matching started. We'll notify you about new leads.")
            elif action == "stop":
                self.matcher_service.disable_user(query.from_user.id)
                await query.edit_message_text("Job matching paused.")
            elif action == "view":
                await self._send_profile_summary(query)
            return
        if data.startswith("bid:"):
            job_id = int(data.split(":")[1])
            await self._show_job_details(query, job_id)
        elif data.startswith("cancel:"):
            job_id = int(data.split(":")[1])
            await self._cancel_bid(query, job_id)
        elif data.startswith("sendbid:"):
            job_id = int(data.split(":")[1])
            await self._submit_bid(query, job_id)
        elif data.startswith("cancelbid:"):
            job_id = int(data.split(":")[1])
            await self._cancel_bid_draft(query, job_id)

    async def _send_profile_summary(self, query) -> None:
        profile = self.profile_store.get_profile(query.from_user.id)
        if not profile:
            await query.edit_message_text("No profile found. Use the menu to create one.")
            return
        summary = json.dumps(profile, indent=2)
        escaped = summary.replace("<", "&lt;").replace(">", "&gt;")
        await query.edit_message_text(
            f"<b>Profile data:</b>\n<pre>{escaped}</pre>",
            parse_mode=ParseMode.HTML,
        )

    async def _show_job_details(self, query, job_id: int) -> None:
        record = self.job_state_store.get_job(query.from_user.id, job_id)
        if not record:
            await query.edit_message_text("Unable to load this job anymore.")
            return
        job = FreelancerJob(**record["payload"])
        self.job_state_store.update_status(query.from_user.id, job_id, "bid_requested")
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✍️ Enter bid",
                        web_app=WebAppInfo(url=self._build_bid_form_url(job)),
                    )
                ],
                [InlineKeyboardButton("✖️ Cancel", callback_data=f"cancel:{job.project_id}")],
            ]
        )
        await query.edit_message_text(
            job.details_html(),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )

    async def _cancel_bid(self, query, job_id: int) -> None:
        self.job_state_store.update_status(query.from_user.id, job_id, "bid_cancelled")
        await query.edit_message_text("Bid cancelled.")

    async def _cancel_bid_draft(self, query, job_id: int) -> None:
        self.job_state_store.update_status(query.from_user.id, job_id, "bid_draft_cancelled")
        await query.edit_message_text("Bid draft discarded.")

    async def _submit_bid(self, query, job_id: int) -> None:
        record = self.job_state_store.get_job(query.from_user.id, job_id)
        if not record:
            await query.edit_message_text("Job details missing. Try fetching again.")
            return
        metadata = self.job_state_store.get_bid_metadata(query.from_user.id, job_id)
        if not metadata:
            await query.edit_message_text("No bid draft found. Please enter bid details again.")
            return
        job = FreelancerJob(**record["payload"])
        amount = metadata.get("amount")
        period = metadata.get("period")
        cover_letter = metadata.get("cover_letter")
        if amount is None or period is None or not cover_letter:
            await query.edit_message_text("Incomplete bid information. Please re-submit the bid form.")
            return

        success, message = await asyncio.get_event_loop().run_in_executor(
            None,
            create_bid,
            job.project_id,
            amount,
            period,
            100,
            cover_letter,
        )
        if success:
            self.job_state_store.mark_bid_result(query.from_user.id, job.project_id, "bid_confirmed")
            text = (
                f"✅ Bid submitted for <b>{html.escape(job.title)}</b>\n"
                f"<b>Amount:</b> {job.currency} {amount}\n"
                f"<b>Period:</b> {period} days\n\n"
                f"<b>Proposal:</b>\n{html.escape(cover_letter)}"
            )
        else:
            self.job_state_store.mark_bid_result(query.from_user.id, job.project_id, "bid_failed", message)
            text = f"⚠️ Unable to submit bid: {html.escape(message)}"
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)

    async def _drain_job_queue(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        while True:
            try:
                user_id, job = self.matcher_service.queue.get_nowait()
            except Empty:
                break
            await self._send_job_to_user(context, user_id, job)

    async def _send_job_to_user(self, context, user_id: int, job: FreelancerJob) -> None:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("💼 Bid this job", callback_data=f"bid:{job.project_id}"),
                ]
            ]
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=job.summary_html(),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
        self.job_state_store.update_status(user_id, job.project_id, "presented")

    @staticmethod
    def _build_experience_summary(profile: dict) -> str:
        parts = []
        if profile.get("experience"):
            parts.append(profile["experience"])
        if profile.get("skills"):
            if isinstance(profile["skills"], list):
                parts.append(", ".join(profile["skills"]))
            else:
                parts.append(profile["skills"])
        if profile.get("positions"):
            if isinstance(profile["positions"], list):
                parts.append("Roles: " + ", ".join(profile["positions"]))
            else:
                parts.append(f"Role: {profile['positions']}")
        return "\n".join(parts)

    @staticmethod
    def _suggest_bid_amount(job: FreelancerJob, profile: dict) -> float:
        if job.job_type == "hourly" and profile.get("hourly_rate"):
            try:
                return float(profile["hourly_rate"])
            except ValueError:
                pass
        if job.budget_min and job.budget_max:
            return (job.budget_min + job.budget_max) / 2
        if job.budget_min:
            return job.budget_min
        if job.budget_max:
            return job.budget_max
        if profile.get("fixed_rate_min") and profile.get("fixed_rate_max"):
            try:
                return (float(profile["fixed_rate_min"]) + float(profile["fixed_rate_max"])) / 2
            except ValueError:
                pass
        return 100.0

    def _build_bid_form_url(self, job: FreelancerJob) -> str:
        params = urlencode(
            {
                "job_id": job.project_id,
                "title": job.title,
                "currency": job.currency,
            }
        )
        return f"{self.settings.webapp.bid_form_url}?{params}"

    async def _process_bid_form_submission(self, update: Update, user_id: int, form_data: dict) -> None:
        job_id = form_data.get("job_id")
        if not job_id:
            await update.effective_message.reply_text("Missing job identifier in the bid form.")
            return
        try:
            job_id = int(job_id)
        except ValueError:
            await update.effective_message.reply_text("Invalid job identifier received.")
            return
        record = self.job_state_store.get_job(user_id, job_id)
        if not record:
            await update.effective_message.reply_text("Could not load job details for this bid.")
            return
        job = FreelancerJob(**record["payload"])
        profile = self.profile_store.get_profile(user_id)
        if not profile:
            await update.effective_message.reply_text("Profile missing. Please complete your profile first.")
            return

        try:
            amount = float(form_data.get("amount"))
            period = int(form_data.get("period"))
        except (TypeError, ValueError):
            await update.effective_message.reply_text("Please provide numeric values for amount and period.")
            return

        sample_jobs = form_data.get("sample_jobs")
        experience_summary = self._build_experience_summary(profile)
        cover_letter = await asyncio.get_event_loop().run_in_executor(
            None,
            generate_cover_letter,
            job.title,
            job.full_description or job.preview_description,
            experience_summary,
            "You are a professional freelancer writing creative proposals for job applications.",
            sample_jobs or profile.get("sample_link"),
        )

        metadata = {
            "amount": amount,
            "period": period,
            "sample_jobs": sample_jobs,
            "cover_letter": cover_letter,
        }
        self.job_state_store.save_bid_metadata(user_id, job_id, metadata)
        self.job_state_store.update_status(user_id, job_id, "bid_draft")

        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Send bid", callback_data=f"sendbid:{job_id}")],
                [
                    InlineKeyboardButton(
                        "✍️ Edit bid",
                        web_app=WebAppInfo(url=self._build_bid_form_url(job)),
                    )
                ],
                [InlineKeyboardButton("✖️ Cancel", callback_data=f"cancelbid:{job_id}")],
            ]
        )
        text = (
            f"<b>{html.escape(job.title)}</b>\n"
            f"<b>Amount:</b> {job.currency} {amount}\n"
            f"<b>Period:</b> {period} days\n\n"
            f"<b>Proposal draft:</b>\n{html.escape(cover_letter)}\n\n"
            "Send this proposal?"
        )
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


def run_bot() -> None:
    settings = load_settings()
    base_path = Path(__file__).resolve().parent.parent
    profile_store = ProfileStore(base_path / "profile.json")
    job_state_store = JobStateStore(base_path / "fetched_jobs_for_users.json")
    matcher_service = JobMatcherService(
        profile_store,
        job_state_store,
        settings.service.fetch_interval_seconds,
        settings.service.max_jobs_per_user,
    )
    matcher_service.start()

    bot = JobMatcherBot(settings, profile_store, job_state_store, matcher_service)
    bot.setup_handlers()
    bot.application.run_polling()
