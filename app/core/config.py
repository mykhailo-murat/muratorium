from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "local"
    database_url: str
    redis_url: str

    telegram_bot_token: str | None = None
    telegram_channel_id: str | None = None

    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    llm_enabled: bool = False
    llm_batch_size: int = 25
    digest_window_hours: int = 12
    digest_top_n: int = 10
    digest_min_score: int = 70
    digest_max_candidates: int = 120

    urgent_threshold: int = 8
    confidence_threshold: float = 0.7
    urgent_rate_limit_per_hour: int = 6
    digest_threshold: int = 6

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
