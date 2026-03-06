from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/meta_scraper"

    # Scraper pool
    pool_max_instances: int = 5

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Browser
    headless: bool = False  # visible for debugging by default

    model_config = {"env_prefix": "META_SCRAPER_"}


settings = Settings()
