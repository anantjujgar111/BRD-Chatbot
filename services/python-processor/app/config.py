from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROOT = Path(__file__).resolve().parents[1]
ENV_CANDIDATES = [
    PROJECT_ROOT / ".env",
    SERVICE_ROOT / ".env",
    Path(".env"),
]


def _resolve_env_file() -> str | None:
    for env_path in ENV_CANDIDATES:
        if env_path.exists():
            return str(env_path)
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        extra="ignore",
    )

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5"
    data_dir: Path = PROJECT_ROOT / "data"
    database_url: str = f"sqlite:///{(PROJECT_ROOT / 'data' / 'brd.db').as_posix()}"
    chroma_dir: str = str(PROJECT_ROOT / "data" / "chroma")
    upload_dir: str = str(PROJECT_ROOT / "data" / "uploads")
    chunk_size: int = 800
    chunk_overlap: int = 150
    retrieval_top_k: int = 12
    rerank_top_k: int = 8


settings = Settings()
