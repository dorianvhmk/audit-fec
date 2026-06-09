from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    supabase_url: str
    supabase_key: str
    cors_origin: str = "http://localhost:5173"

    class Config:
        env_file = ".env"


settings = Settings()
