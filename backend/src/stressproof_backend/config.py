"""
Configuration management using pydantic-settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    API_WRITE_TOKEN: str = "stressproof_dev_token_secret"
    BACKEND_PUBLIC_URL: str = "http://127.0.0.1:8000"
    DATA_DIR: str = "./data"
    CORS_ORIGINS: str = "http://localhost:3000"

    FETCH_MAX_BYTES: int = 26214400
    FETCH_TIMEOUT_SEC: int = 10
    FETCH_ALLOW_LOCALHOST: bool = True

    MARKET_ID_STRING: str = "aave-v3-eth-weth-stable"


settings = Settings()
