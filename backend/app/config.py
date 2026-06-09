from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    supabase_url: str
    supabase_key: str
    # Comma-separated list of allowed origins, or "*" to allow all.
    # Default to "*" so Railway works without explicit env var configuration.
    cors_origin: str = "*"

    class Config:
        env_file = ".env"


settings = Settings()
