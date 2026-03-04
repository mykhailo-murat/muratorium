from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "local"
    database_url: str
    redis_url: str

    telegram_bot_token: str | None = None
    telegram_channel_id: str | None = None

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
