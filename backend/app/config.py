"""
앱 설정 (환경변수 기반)
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/automated_posting"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24시간

    # LLM API Keys
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # SNS API Keys
    x_api_key: str = ""
    x_api_secret: str = ""
    x_access_token: str = ""
    x_access_secret: str = ""
    x_bearer_token: str = ""

    meta_app_id: str = ""
    meta_app_secret: str = ""
    instagram_access_token: str = ""
    instagram_account_id: str = ""

    youtube_api_key: str = ""

    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""

    # Media
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""
    elevenlabs_api_key: str = ""

    # Naver
    naver_client_id: str = ""
    naver_client_secret: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
