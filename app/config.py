"""
Settings — loaded from environment variables via pydantic-settings.
Supports .env file for local development.
"""
from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # Groq
    groq_api_key: str = "gsk_your_groq_api_key_here"
    groq_model: str = "llama3-70b-8192"

    # Supabase
    supabase_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    supabase_service_key: Optional[str] = None

    # App
    app_env: str = "development"
    secret_key: str = "change_me_to_32_char_string"
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"

    # Hallucination guard
    hallucination_samples: int = 3
    hallucination_threshold: float = 0.4

    # Bias metrics
    bias_disparity_threshold: float = 0.10

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
