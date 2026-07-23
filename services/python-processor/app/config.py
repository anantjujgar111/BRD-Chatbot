from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    data_dir: Path = Path("../../data")
    database_url: str = "sqlite:///../../data/brd.db"
    chroma_dir: str = "../../data/chroma"
    upload_dir: str = "../../data/uploads"
    chunk_size: int = 800
    chunk_overlap: int = 150
    retrieval_top_k: int = 12
    rerank_top_k: int = 8


settings = Settings()
