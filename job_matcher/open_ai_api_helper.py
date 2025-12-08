from __future__ import annotations

import logging
from typing import Optional

from openai import OpenAI

from .config import load_settings

logger = logging.getLogger(__name__)
settings = load_settings()
OPENAI_API_KEY = settings.openai.api_key


def generate_cover_letter(
    project_title: str,
    project_description: str,
    experience_summary: str,
    context: str = "You are a professional freelancer writing creative proposals for job applications.",
    sample_link: Optional[str] = None,
) -> str:
    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        user_content = (
            "Summarize relevant experience and suggest technical solutions for this job. "
            "Do not include any personal information, names, addresses, or references to the client. "
            "Focus only on professional experience and how to approach the project in the best way.\n"
            f"Project Title: {project_title}\n"
            f"Project Description: {project_description}\n"
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

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": context},
                {"role": "user", "content": user_content},
            ],
            max_tokens=200,
            temperature=0.7,
        )
        cover_letter = response.choices[0].message.content.strip()
        if valid_sample_link:
            links = [link.strip() for link in sample_link.split(",") if len(link.strip()) >= 10]
            if links:
                cover_letter += "\n\nYou can view my sample project(s) here:\n"
                for link in links:
                    cover_letter += f"- {link}\n"
        return cover_letter
    except Exception as exc:
        logger.exception("Error generating cover letter: {exc}")
        return (
            "Experienced in similar projects. I propose using proven technologies "
            "and best practices to deliver optimal results."
        )
