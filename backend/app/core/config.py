import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Le .env vit à la racine du dépôt (partagé avec docker-compose plus tard).
ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str | None = None
    gemini_chat_model: str = "gemini-3.8-flash"
    gemini_live_model: str = "gemini-2.5-flash-native-audio-preview-09-2025"
    # NoDecode : sans lui, pydantic-settings tente un json.loads() sur la valeur du .env
    # avant notre validateur, ce qui échoue pour `CORS_ORIGINS=http://localhost:5173`.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    @field_validator("gemini_api_key", mode="before")
    @classmethod
    def _blank_key_is_none(cls, value: str | None) -> str | None:
        # `GEMINI_API_KEY=` (valeur vide dans .env.example) équivaut à « non configurée ».
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        # Accepte `CORS_ORIGINS=http://a,http://b` ou une liste JSON `["http://a"]`.
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                return json.loads(value)
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
