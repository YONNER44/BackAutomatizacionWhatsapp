from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AutomatizacionWhatsapp"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Google Sheets (opcional)
    GOOGLE_APPLICATION_CREDENTIALS: str = ""
    GOOGLE_SHEET_ID: str = ""

    # Base de datos
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/automatizacion"

    # Excel output
    EXCEL_OUTPUT_PATH: str = "./output/precios.xlsx"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
