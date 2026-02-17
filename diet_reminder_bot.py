"""
Diet reminder bot:
- Sends WhatsApp reminders at scheduled times.
- Loads secure config from .env.
- Writes logs to logs/reminder_bot.log.
- Forward-only behavior: no missed catch-up, no retries.

Uses Twilio WhatsApp API.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import os
from dotenv import load_dotenv
from twilio.rest import Client


BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "reminder_bot.log"


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)


@dataclass(frozen=True)
class ReminderItem:
    time_24h: str
    title: str
    details: str


DAILY_PLAN = [
    ReminderItem(
        "08:30",
        "Morning dry fruits and seeds",
        "It is 8:30 AM. Please take soaked almonds, walnuts, cranberry, seeds, and figs.",
    ),
    ReminderItem(
        "09:30",
        "Breakfast",
        "It is 9:30 AM. Please have breakfast now.",
    ),
    ReminderItem(
        "10:30",
        "Coconut water",
        "It is 10:30 AM. Please drink coconut water now.",
    ),
    ReminderItem(
        "11:30",
        "Folic acid and iron",
        "It is 11:30 AM. Please take folic acid medicine and iron medicine now.",
    ),
    ReminderItem(
        "13:30",
        "Lunch, salad, and iron",
        "It is 1:30 PM. Please have lunch and salad, and also take iron medicine.",
    ),
    ReminderItem(
        "15:00",
        "Afternoon fruits",
        "It is 3:00 PM. Please eat orange, anaar, and apple.",
    ),
    ReminderItem(
        "17:00",
        "Snack and tea",
        "It is 5:00 PM. Please have snack and tea now.",
    ),
    ReminderItem(
        "20:15",
        "Magnesium before dinner",
        "It is before dinner time. Please take magnesium medicine now.",
    ),
    ReminderItem(
        "20:30",
        "Dinner with eggs and salad",
        "It is 8:30 PM. Please have dinner, 2 eggs, and salad.",
    ),
    ReminderItem(
        "22:00",
        "Milk",
        "It is 10:00 PM. Please drink milk now.",
    ),
    ReminderItem(
        "22:30",
        "Ecosprin before sleep",
        "It is bedtime. Please take ecosprin medicine before sleep.",
    ),
]


@dataclass(frozen=True)
class AppConfig:
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_number: str
    sister_whatsapp_number: str
    timezone: str
    start_date: date
    calcium_reminder_weekday: int
    calcium_reminder_time: str
    poll_interval_seconds: int


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _normalize_whatsapp_number(raw: str, env_name: str) -> str:
    value = raw.strip()
    if value.startswith("whatsapp:"):
        return value
    if not value.startswith("+"):
        raise ValueError(
            f"{env_name} must be in E.164 format like +91XXXXXXXXXX or whatsapp:+91XXXXXXXXXX"
        )
    return f"whatsapp:{value}"


def load_config() -> AppConfig:
    load_dotenv(dotenv_path=BASE_DIR / ".env")
    return AppConfig(
        twilio_account_sid=_require_env("TWILIO_ACCOUNT_SID"),
        twilio_auth_token=_require_env("TWILIO_AUTH_TOKEN"),
        twilio_whatsapp_number=_normalize_whatsapp_number(
            _require_env("TWILIO_WHATSAPP_NUMBER"), "TWILIO_WHATSAPP_NUMBER"
        ),
        sister_whatsapp_number=_normalize_whatsapp_number(
            _require_env("SISTER_WHATSAPP_NUMBER"), "SISTER_WHATSAPP_NUMBER"
        ),
        timezone=os.getenv("TIMEZONE", "Asia/Kolkata"),
        start_date=date.fromisoformat(os.getenv("START_DATE", "2026-02-21")),
        calcium_reminder_weekday=int(os.getenv("CALCIUM_REMINDER_WEEKDAY", "5")),
        calcium_reminder_time=os.getenv("CALCIUM_REMINDER_TIME", "09:00"),
        poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "20")),
    )


def build_whatsapp_message(item: ReminderItem, now_local: datetime) -> str:
    human_time = now_local.strftime("%I:%M %p")
    return (
        f"Reminder ({human_time}): {item.title}\n"
        f"{item.details}\n"
        "Please take care."
    )


def send_whatsapp(client: Client, to_whatsapp: str, from_whatsapp: str, message: str) -> None:
    client.messages.create(
        from_=from_whatsapp,
        to=to_whatsapp,
        body=message,
    )


def trigger_event(
    client: Client,
    now_local: datetime,
    item: ReminderItem,
    config: AppConfig,
) -> None:
    wa_msg = build_whatsapp_message(item, now_local)
    send_whatsapp(
        client,
        config.sister_whatsapp_number,
        config.twilio_whatsapp_number,
        wa_msg,
    )
    return


def run() -> None:
    setup_logging()
    config = load_config()
    tz = ZoneInfo(config.timezone)
    client = Client(config.twilio_account_sid, config.twilio_auth_token)
    sent_keys: set[str] = set()
    last_seen_date = None

    logging.info("Diet reminder bot started")
    logging.info("Timezone=%s | Start date=%s", config.timezone, config.start_date.isoformat())

    while True:
        now_local = datetime.now(tz=tz).replace(second=0, microsecond=0)
        today = now_local.date()
        current_hm = now_local.strftime("%H:%M")

        if today < config.start_date:
            time.sleep(config.poll_interval_seconds)
            continue

        if last_seen_date != today:
            sent_keys.clear()
            last_seen_date = today

        for item in DAILY_PLAN:
            if item.time_24h != current_hm:
                continue

            key = f"{today.isoformat()}-{item.time_24h}-{item.title}"
            if key in sent_keys:
                continue

            logging.info("Attempting reminder | key=%s", key)
            try:
                trigger_event(client, now_local, item, config)
                logging.info("Reminder success | key=%s", key)
            except Exception as exc:  # noqa: BLE001
                logging.exception("Reminder failed | key=%s | error=%s", key, exc)
            finally:
                # Forward-only: do not retry this slot after one attempt.
                sent_keys.add(key)

        # Weekly calcium reminder is intentionally disabled for one-reminder testing.

        time.sleep(config.poll_interval_seconds)


if __name__ == "__main__":
    run()
