import configparser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.ini"


@dataclass
class TelegramSettings:
    bot_token: str
    menu_photo_url: Optional[str] = None


@dataclass
class FreelancerSettings:
    api_token: str
    api_base: str


@dataclass
class OpenAISettings:
    api_key: str


@dataclass
class WebAppSettings:
    base_url: str


@dataclass
class ServiceSettings:
    fetch_interval_seconds: int = 120
    max_jobs_per_user: int = 5


@dataclass
class Settings:
    telegram: TelegramSettings
    freelancer: FreelancerSettings
    openai: OpenAISettings
    webapp: WebAppSettings
    service: ServiceSettings


def _read_config(path: Path = CONFIG_PATH) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    if not path.exists():
        raise FileNotFoundError(
            f"Missing config.ini file at {path}. Please create it from config.example.ini"
        )
    parser.read(path)
    return parser


def load_settings(path: Path = CONFIG_PATH) -> Settings:
    parser = _read_config(path)

    telegram = TelegramSettings(
        bot_token=parser.get("telegram", "bot_token", fallback="").strip(),
        menu_photo_url=parser.get("telegram", "menu_photo_url", fallback=None),
    )
    if not telegram.bot_token:
        raise ValueError("Telegram bot token is missing from config.ini")

    freelancer = FreelancerSettings(
        api_token=parser.get("freelancer", "api_token", fallback="").strip(),
        api_base=parser.get("freelancer", "api_base", fallback="").strip(),
    )
    if not freelancer.api_token:
        raise ValueError("Freelancer API token is missing from config.ini")

    openai_settings = OpenAISettings(
        api_key=parser.get("openai", "api_key", fallback="").strip()
    )
    if not openai_settings.api_key:
        raise ValueError("OpenAI API key is missing from config.ini")

    webapp = WebAppSettings(
        base_url=parser.get("webapp", "base_url", fallback="http://localhost:8000/webapp")
    )

    service = ServiceSettings(
        fetch_interval_seconds=parser.getint("service", "fetch_interval_seconds", fallback=120),
        max_jobs_per_user=parser.getint("service", "max_jobs_per_user", fallback=5),
    )

    return Settings(
        telegram=telegram,
        freelancer=freelancer,
        openai=openai_settings,
        webapp=webapp,
        service=service,
    )
