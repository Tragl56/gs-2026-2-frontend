"""Configuração central do back-end, lida de variáveis de ambiente / .env.

Nenhum segredo fica no código: a chave do LLM vem de GEMINI_API_KEY.
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    llm_provider: str = Field(default="gemini", description="gemini | mock")
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    llm_timeout_seconds: float = 25.0

    # Segurança
    cors_origins: str = "http://localhost:8501"
    manager_token: str = "troque-este-token"
    analyze_rate_limit_per_minute: int = 10

    # Dados
    database_path: str = "data/zela.db"
    seed_demo_data: bool = False
    viacep_url: str = "https://viacep.com.br/ws"
    open_data_timeout_seconds: float = 4.0
    similar_window_days: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        # Nunca liberamos "*": se alguém configurar, é descartado.
        return [o for o in origins if o != "*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
