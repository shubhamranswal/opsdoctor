"""Configuration module for OpsDoctor.

Centralizes runtime settings, environment variables, filesystem paths, and defaults.
Supports production hosting, container environments, and local development.
"""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


def _resolve_swytchcode_bin() -> str:
    """Locate the Swytchcode CLI binary."""
    env_bin = os.getenv("SWYTCHCODE_BIN")
    if env_bin and os.path.exists(env_bin):
        return env_bin

    local_app_data = os.getenv("LOCALAPPDATA", "")
    if local_app_data:
        win_path = Path(local_app_data) / "Programs" / "swytchcode" / "bin" / "swytchcode.exe"
        if win_path.exists():
            return str(win_path)

    import shutil
    which_bin = shutil.which("swytchcode") or shutil.which("swy")
    if which_bin:
        return which_bin

    return "swytchcode"


class Settings(BaseModel):
    """OpsDoctor application configuration settings."""

    # Application metadata
    app_name: str = "OpsDoctor"
    app_version: str = "2.0.0"
    app_env: str = Field(default_factory=lambda: os.getenv("APP_ENV", "production"))
    debug: bool = Field(default_factory=lambda: os.getenv("DEBUG", "false").lower() in ("true", "1", "yes"))

    # Server binding
    host: str = Field(default_factory=lambda: os.getenv("HOST", "127.0.0.1"))
    port: int = Field(default_factory=lambda: int(os.getenv("PORT", "8000")))

    # AI & Cognitive Engine
    gemini_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", "").strip() or None)
    gemini_model: str = Field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.8-flash"))

    # Execution Kernel (Swytchcode)
    swytchcode_bin: str = Field(default_factory=_resolve_swytchcode_bin)
    swytchcode_timeout_seconds: int = Field(default_factory=lambda: int(os.getenv("SWYTCHCODE_TIMEOUT", "30")))

    # Filesystem Paths
    base_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    data_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "data")
    fixtures_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "data" / "fixtures")
    sessions_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "data" / "sessions")

    # Logging
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    class Config:
        arbitrary_types_allowed = True

    def ensure_directories(self) -> None:
        """Ensure all required runtime data and session directories exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.fixtures_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)


# Singleton settings instance
settings = Settings()
settings.ensure_directories()
