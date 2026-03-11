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
    urgent_llm_batch_size: int = 12
    digest_window_hours: int = 12
    digest_top_n: int = 10
    digest_min_score: int = 70
    digest_max_candidates: int = 1200
    fast_lane_enabled: bool = True
    fast_poll_seconds: int = 120
    fast_min_sources: int = 2
    fast_score_threshold: int = 90
    fast_title_similarity: int = 85
    cleanup_enabled: bool = True
    cleanup_hour: int = 4
    cleanup_minute: int = 30
    cleanup_batch_size: int = 5000
    cleanup_keep_published_days: int = 30
    cleanup_keep_unpublished_days: int = 7
    cleanup_keep_messages_days: int = 30

    urgent_threshold: int = 8
    confidence_threshold: float = 0.7
    urgent_rate_limit_per_hour: int = 6
    digest_threshold: int = 7
    urgent_prefilter_enabled: bool = True
    urgent_prefilter_threshold: int = 80
    urgent_rescore_cooldown_minutes: int = 45
    log_level: str = "INFO"
    log_file_path: str = "logs/pipeline.log"
    log_rotation_days: int = 3
    log_backup_count: int = 1

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
