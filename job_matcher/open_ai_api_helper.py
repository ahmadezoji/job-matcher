from __future__ import annotations

import logging
from typing import Optional

import requests

from .config import load_settings

logger = logging.getLogger(__name__)
settings = load_settings()
OPENAI_API_KEY = settings.openai.api_key
OPENAI_CHAT_COMPLETION_URL = "https://api.openai.com/v1/chat/completions"


def generate_cover_letter(
    project_title: str,
    project_description: str,
    experience_summary: str,
    context: str = "You are a professional freelancer writing creative proposals for job applications.",
    sample_link: Optional[str] = None,
    user_notes: Optional[str] = None,
) -> str:
    if not OPENAI_API_KEY:
        logger.error("OpenAI API key missing")
        return (
            "Experienced in similar projects. I propose using proven technologies "
            "and best practices to deliver optimal results."
        )
    try:
        user_content = (
            "Write a genuine, conversational cover letter for a freelancer applying to a project. "
            "The tone should feel like a real person wrote it—natural, confident, and personable. "
            "Avoid corporate jargon, generic phrases like 'I am excited to apply', or overly formal language. "
            "Write as if you're having a direct conversation with the client.\n\n"
            "IMPORTANT GUIDELINES:\n"
            "- Start by showing you actually read and understood their project (reference specific details)\n"
            "- Share a brief, relevant story or example from past work that connects to their needs\n"
            "- Be specific about HOW you would approach their project, not just THAT you can do it\n"
            "- Show genuine curiosity or insight about their project\n"
            "- Keep it concise (2-3 short paragraphs max)\n"
            "- No greetings like 'Dear Sir/Madam' or sign-offs like 'Best regards'\n"
            "- Don't invent names or details not provided\n"
            "- End with a natural call-to-action, like asking a clarifying question or suggesting next steps\n\n"
            f"PROJECT TITLE: {project_title}\n"
            f"PROJECT DESCRIPTION: {project_description}\n"
            f"MY RELEVANT EXPERIENCE: {experience_summary or 'General freelancing experience.'}\n"
        )

        if user_notes and user_notes.strip():
            user_content += (
                f"\nSPECIAL INSTRUCTIONS FROM ME (incorporate these naturally into the letter):\n"
                f"{user_notes}\n"
            )

        valid_sample_link = (
            sample_link
            and isinstance(sample_link, str)
            and len(sample_link.strip()) >= 10
            and sample_link.strip() not in ["", " ", "-", "_", ".", ",", "x", "X"]
        )
        if valid_sample_link:
            user_content += f"\nSAMPLE PROJECT LINK (mention naturally if relevant): {sample_link}\n"

        user_content += "\nRemember: Sound like a real human, not a template. Be specific and genuine."

        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": context},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": 300,
            "temperature": 0.7,
        }
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        response = requests.post(
            OPENAI_CHAT_COMPLETION_URL,
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("No choices returned from OpenAI")
        cover_letter = choices[0]["message"]["content"].strip()
        if valid_sample_link:
            links = [link.strip() for link in sample_link.split(",") if len(link.strip()) >= 10]
            if links:
                cover_letter += "\n\nYou can view my sample project(s) here:\n"
                for link in links:
                    cover_letter += f"- {link}\n"
        return cover_letter
    except Exception as exc:
        logger.exception("Error generating cover letter: %s", exc)
        return (
            "Experienced in similar projects. I propose using proven technologies "
            "and best practices to deliver optimal results."
        )
