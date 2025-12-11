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
) -> str:
    if not OPENAI_API_KEY:
        logger.error("OpenAI API key missing")
        return (
            "Experienced in similar projects. I propose using proven technologies "
            "and best practices to deliver optimal results."
        )
    try:
        user_content = (
            "Write a concise, human-sounding cover letter for a freelancer. "
            "Keep it warm but professional, as if written by the freelancer directly. "
            "Structure it into two short paragraphs: "
            "1) highlight the most relevant past experience and tools; "
            "2) explain how those skills solve the client's needs and why the client should pick this freelancer. "
            "Avoid filler, personal contact info, or repetition.\n"
            f"Project Title: {project_title}\n"
            f"Project Description: {project_description}\n"
            f"My Relevant Experience: {experience_summary or 'Use the context above.'}\n"
            "End with a confident sentence about readiness to start."
        )
        if experience_summary:
            user_content += f"My Relevant Experience: {experience_summary}\n"
        valid_sample_link = (
            sample_link
            and isinstance(sample_link, str)
            and len(sample_link.strip()) >= 10
            and sample_link.strip() not in ["", " ", "-", "_", ".", ",", "x", "X"]
        )
        if valid_sample_link:
            user_content += f"Here is a sample project I have worked on: {sample_link}\n"
        user_content += "Keep it concise, professional, and solution-oriented."

        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": context},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": 200,
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
