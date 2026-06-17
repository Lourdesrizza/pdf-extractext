from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApplicationSettings(BaseSettings):
    """Configuración central de la aplicación."""

    # Estos nombres deben matchear con tu archivo .env
    API_V1_STR: str
    DEBUG: bool
    DATABASE_URL: str
    DB_NAME: str
    SECRET_KEY: str

    # Esta es la forma moderna (Pydantic V2) de cargar el .env
    model_config = SettingsConfigDict(env_file=".env")

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        """Acepta valores comunes de entorno como release/development."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "false", "0", "no"}:
                return False
            if normalized in {"dev", "development", "true", "1", "yes"}:
                return True
        return value


# Instanciamos para que el resto de la app lo use
settings = ApplicationSettings()
