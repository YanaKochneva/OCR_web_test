"""Runtime configuration, loaded from the project `.env` file.

Every secret is read from the environment - nothing is hardcoded.  See
`.env.example` for the full list of supported variables.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/app -> backend -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings (env vars win over the `.env` file)."""

    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", str(PROJECT_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "GLM 4.6 Document Extraction Benchmark"
    debug: bool = False

    # --- GLM credentials -------------------------------------------------
    glm_api_key: str = ""
    glm_base_url: str = "https://api.z.ai/api/paas/v4/"
    glm_model: str = "glm-4.6v"
    glm_model_fallbacks: str = "glm-4.6v-flash,glm-4.5v"
    glm_temperature: float = 0.1
    glm_max_tokens: int = 8192
    glm_timeout_seconds: float = 180.0
    glm_max_retries: int = 2
    glm_json_mode: bool = True
    glm_mock: bool = False

    # --- uploads ----------------------------------------------------------
    max_upload_mb: int = 50
    allowed_extensions: str = ".pdf,.docx"

    # --- rendering --------------------------------------------------------
    render_dpi: int = 200
    render_max_pages: int = 50
    renderer_backend: str = "pymupdf"
    text_layer_min_chars: int = 20

    # --- storage / cors ---------------------------------------------------
    data_dir: str = "./data"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ------------------------------------------------------------------ #
    # derived helpers
    # ------------------------------------------------------------------ #
    @property
    def api_key(self) -> str:
        """GLM key, accepting either platform's conventional variable name."""
        return (
            self.glm_api_key
            or os.getenv("ZAI_API_KEY", "")
            or os.getenv("ZHIPUAI_API_KEY", "")
            or ""
        ).strip()

    @property
    def model_candidates(self) -> list[str]:
        """Configured model first, then the fallbacks, de-duplicated."""
        chain = [self.glm_model, *self.glm_model_fallbacks.split(",")]
        seen: list[str] = []
        for name in chain:
            name = name.strip()
            if name and name not in seen:
                seen.append(name)
        return seen

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def allowed_suffixes(self) -> set[str]:
        return {
            ext.strip().lower()
            for ext in self.allowed_extensions.split(",")
            if ext.strip()
        }

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def data_path(self) -> Path:
        path = Path(self.data_dir)
        if not path.is_absolute():
            path = (PROJECT_ROOT / path).resolve()
        path.mkdir(parents=True, exist_ok=True)
        (path / "images").mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
