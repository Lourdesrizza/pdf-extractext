from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApplicationSettings(BaseSettings):
    """Configuración central de la aplicación."""

    # Estos nombres deben matchear con tu archivo .env
    API_V1_STR: str
    DEBUG: bool
    DB_NAME: str
    SECRET_KEY: str

    # Host y puerto de MongoDB leidos dinamicamente del entorno.
    # Por defecto apuntan a localhost para poder correr fuera de Docker;
    # dentro de Docker se sobreescriben (ej. MONGO_HOST=basededatos).
    MONGO_HOST: str = "localhost"
    MONGO_PORT: int = 27017

    # URI completa opcional: si se setea, tiene prioridad sobre host/puerto.
    # Util para entornos con credenciales o servicios gestionados (ej. Atlas).
    DATABASE_URL: str | None = None

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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """URI de conexion a MongoDB.

        Si DATABASE_URL esta definido (override total), se usa tal cual.
        Si no, se arma dinamicamente con MONGO_HOST y MONGO_PORT.
        """
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"mongodb://{self.MONGO_HOST}:{self.MONGO_PORT}"


# Instanciamos para que el resto de la app lo use
settings = ApplicationSettings()
