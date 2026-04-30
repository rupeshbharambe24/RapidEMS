"""Application settings loaded from environment variables / .env file."""
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", "../.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ──
    database_url: str = "sqlite:///./emergency.db"

    # ── Security ──
    secret_key: str = "dev-only-change-me-please-use-a-long-random-string-32-chars"
    access_token_expire_minutes: int = 1440
    algorithm: str = "HS256"

    # ── App ──
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = True
    log_level: str = "INFO"

    # ── ML ──
    models_dir: Path = Path("./ai_models")
    allow_heuristic_fallback: bool = True

    # ── LLM extraction (optional) ──
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    llm_provider_order: str = "groq,gemini"

    # ── Routing providers (optional, all free tier) ──
    # Chain order: OSRM (self-hosted, unlimited) -> ORS (2000/day) ->
    # HERE (250K/month) -> haversine. Empty values skip that provider.
    osrm_url: str = ""                 # e.g. http://localhost:5000
    ors_api_key: str = ""              # https://openrouteservice.org/dev/
    mapbox_api_key: str = ""           # https://account.mapbox.com/
    here_api_key: str = ""             # https://platform.here.com/
    # Blend weight for road ETA vs ML ETA when both are available.
    eta_road_weight: float = 0.7

    # Helicopter dispatch tier — air alternative for SEV-1 calls when
    # ground transit is far enough that the lift+land overhead pays for
    # itself. Speed in km/h; setup is ground-time before takeoff + after
    # landing in minutes.
    helicopter_speed_kmh: float = 220.0
    helicopter_setup_minutes: float = 4.0
    # Only consider air dispatch when ground ETA is at least this many
    # minutes longer than the air alternative.
    helicopter_min_savings_minutes: float = 6.0
    # Furthest helipad we'll fly to from the scene.
    helicopter_max_range_km: float = 60.0

    # ── Notifications (all optional, all free tier) ──
    # Telegram bot — talk to @BotFather to make one. Recipients must /start
    # the bot once, then their chat_id can receive sendMessage calls.
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""    # without the @ ; for the deep-link CTA
    # SMTP — Gmail "App passwords" or SendGrid free tier (100/day) work.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_from: str = ""
    smtp_from_name: str = "RapidEMS"
    # Twilio (paid, optional). Only enabled when both keys are set.
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    # ── CORS ──
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"

    # ── Seed data ──
    seed_on_startup: bool = True
    seed_city_lat: float = 19.0760
    seed_city_lng: float = 72.8777
    seed_num_ambulances: int = 20
    seed_num_hospitals: int = 8

    # ── Default admin ──
    admin_username: str = "admin"
    admin_password: str = "admin123"
    admin_email: str = "admin@emergency.example.com"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("models_dir", mode="before")
    @classmethod
    def _resolve_models_dir(cls, v):
        return Path(v).resolve() if not isinstance(v, Path) else v.resolve()


settings = Settings()
