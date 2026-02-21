from dotenv import load_dotenv
import os
from functools import lru_cache

# 🔥 This line makes .env work on Windows + Uvicorn
load_dotenv()


class Settings:
    """Application configuration loaded from environment variables."""

    OPENAI_API_KEY: str | None
    OPENAI_MODEL: str
    MONGODB_URI: str
    MONGODB_DB_NAME: str
    ALLOWED_ORIGINS: list[str]

    def __init__(self) -> None:
        # OpenAI
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        self.OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

        # MongoDB
        mongo_uri = os.getenv("MONGODB_URI")
        if not mongo_uri:
            raise RuntimeError("MONGODB_URI is required")

        self.MONGODB_URI = mongo_uri
        self.MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "vertex_ai")

        # CORS Origins
        origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")
        self.ALLOWED_ORIGINS = [o.strip() for o in origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()