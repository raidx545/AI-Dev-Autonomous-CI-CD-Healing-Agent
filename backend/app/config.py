"""
Configuration management for the DevOps Agent backend.
Loads settings from environment variables / .env file.
"""

from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # GitHub
    github_token: str = ""

    # AI Provider (Sarvam AI)
    sarvam_api_key: str = ""

    # Agent behaviour
    max_iterations: int = 5
    clone_base_dir: str = os.path.join(os.path.expanduser("~"), ".devops_agent", "repos")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["*"]

    model_config = {
        "env_file": os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
