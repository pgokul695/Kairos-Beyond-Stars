"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """Centralised settings — no hardcoded values anywhere else."""

    # Database
    database_url: str = Field(..., env="DATABASE_URL")

    # Google AI
    google_api_key: str = Field(..., env="GOOGLE_API_KEY")
    gemma_model: str = Field("gemini-2.5-flash", env="GEMMA_MODEL")
    gemma_fallback_model: str = Field("gemma-3-12b-it", env="GEMMA_FALLBACK_MODEL")
    embedding_model: str = Field("gemini-embedding-001", env="EMBEDDING_MODEL")
    embedding_dimensions: int = Field(768, env="EMBEDDING_DIMENSIONS")

    # Security
    service_token: str = Field(..., env="SERVICE_TOKEN")
    allowed_origins: str = Field(
        "https://kairos.gokulp.online,http://localhost:3000",
        env="ALLOWED_ORIGINS",
    )

    # App
    app_env: str = Field("development", env="APP_ENV")
    log_level: str = Field("INFO", env="LOG_LEVEL")

    # Local ML — all default to false so production behaviour is unchanged
    # until explicitly opted in.
    use_local_embeddings: bool = Field(False, env="USE_LOCAL_EMBEDDINGS")
    use_local_reranker: bool = Field(False, env="USE_LOCAL_RERANKER")
    use_local_classifier: bool = Field(False, env="USE_LOCAL_CLASSIFIER")

    # Derived
    @property
    def allowed_origins_list(self) -> list[str]:
        """Return ALLOWED_ORIGINS as a list."""
        return [o.strip() for o in self.allowed_origins.split(",")]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()


settings = get_settings()
