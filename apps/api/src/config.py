import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # PostgreSQL
    POSTGRES_USER:      str = os.getenv("POSTGRES_USER", "ztd_admin")
    POSTGRES_PASSWORD:  str = os.getenv("POSTGRES_PASSWORD", "ztd_dev_password")
    POSTGRES_DB:        str = os.getenv("POSTGRES_DB", "ztd_iot")
    POSTGRES_HOST:      str = os.getenv("POSTGRES_HOST", "db")
    POSTGRES_PORT:      int = int(os.getenv("POSTGRES_PORT", "5432"))

    # MQTT
    MQTT_HOST: str = os.getenv("MQTT_HOST", "mqtt")
    MQTT_PORT: int = int(os.getenv("MQTT_PORT", "1883"))

    # App
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

settings = Settings()
