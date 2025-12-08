# Job Matcher

End-to-end Python service that:

- exposes a Telegram WebApp mini-form so users can create/update their freelancer profile,
- queues background searches on Freelancer.com that match the stored profile,
- delivers modern job cards back to the Telegram chat with a “Bid this job” CTA,
- generates a cover letter via OpenAI when the user confirms, and finally
- places the bid via the Freelancer API while tracking every job state in `fetched_jobs_for_users.json`.

## 1. Project structure

```
job_matcher/
├── bot.py                    # Telegram bot & callbacks
├── config.py                 # INI loader + strongly typed settings
├── freelancer_api_helper.py  # API search + bid helpers
├── job_matcher_service.py    # Background polling thread
├── job_state_store.py        # Persisted fetched/bid job state
├── open_ai_api_helper.py     # Cover letter helper
├── profile_store.py          # profile.json persistence
├── templates/profile_form.html
├── webapp.py                 # FastAPI mini app host
├── __init__.py
config.ini                    # Fill with your secrets (sample contents committed)
fetched_jobs_for_users.json   # Stores all job states
main.py                       # Entry point (runs the Telegram bot)
profile.json                  # Stores Telegram user profiles
requirements.txt
```

## 2. Configuration

1. Duplicate `config.ini` and populate with real values:

```
[telegram]
bot_token=12345:ABC
menu_photo_url=optional-image-url

[freelancer]
api_token=YOUR_FREELANCER_ACCESS_TOKEN
api_base=https://www.freelancer.com/api/projects/0.1

[openai]
api_key=sk-...

[webapp]
base_url=https://<public-host>/webapp   # or http://<lan-ip>:8000/webapp for testing

[service]
fetch_interval_seconds=120
max_jobs_per_user=5
```

2. Install dependencies (prefer virtualenv):

```bash
pip install -r requirements.txt
```

3. Ensure `profile.json` and `fetched_jobs_for_users.json` are writable by the service; both default to `{}`.

## 3. Running the services

You need the FastAPI WebApp and the Telegram bot running at the same time.

### 3.1 Telegram WebApp form

```bash
uvicorn job_matcher.webapp:app --reload --port 8000
```

Expose the chosen URL publicly (e.g., via [ngrok](https://ngrok.com/)) and update `[webapp].base_url` in `config.ini`. Telegram’s WebApp button uses that absolute URL.

### 3.2 Telegram bot + background matcher

```bash
python main.py
```

What happens at runtime:

1. `/start` shows the control panel & WebApp button (Create/Edit Profile).
2. When the user submits the form, the bot persists the payload in `profile.json`.
3. “Start job matching” spins up a background polling thread (per requirements) that:
   - maps profile preferences into a search query,
   - hits the Freelancer API via `freelancer_api_helper.search_jobs`,
   - deduplicates using `JobStateStore` and enqueues new leads.
4. The bot drains the queue every 5 seconds and sends modern job cards (HTML layout) with a `Bid this job` button.
5. “Bid this job” shows the full description with confirm/cancel buttons.
6. Confirm triggers OpenAI cover-letter generation, then `create_bid` posts it to Freelancer. The final status is written back into `fetched_jobs_for_users.json` (`bid_confirmed`, `bid_failed`, etc.).

All token/ID dependent logic lives in helpers so you can expand to other platforms later.

## 4. Extending to more platforms

- Add dedicated helper modules (e.g., `upwork_api_helper.py`) following the Freelancer pattern.
- Enhance `JobMatcherService._fetch_for_user` to fan out to all enabled platforms per user (`profile["platforms"]`).
- `JobStateStore` is platform-agnostic: store composite keys such as `<platform>-<id>` to track each source independently.

## 5. Testing tips

- Run the WebApp in a desktop browser first; it gracefully falls back by showing the JSON payload so you can copy/paste it into the bot for manual testing.
- Use Telegram’s `/getUpdates` while the bot is running if you prefer long polling for quick debugging.
- Mock `freelancer_api_helper.search_jobs` or point it to stub data when you don’t want to consume API quota.

## 6. Next steps

- Plug in persistence beyond JSON (e.g., Postgres) once you outgrow flat files.
- Add metrics/log shipping (the helpers already log to stdout using `logging`).
- Wire the same background-worker interface to additional freelancing platforms using the `platforms` preference stored per user.
