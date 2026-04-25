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
    gemini_model: str = "gemini-1.5-flash"
    llm_provider_order: str = "groq,gemini"

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
