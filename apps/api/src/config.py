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
    SERVER_HOST: str = os.getenv("SERVER_HOST", "localhost")

    # Presence (heartbeat) window in seconds. Backend is the source of truth.
    DEVICE_ONLINE_WINDOW_SECONDS: int = int(os.getenv("DEVICE_ONLINE_WINDOW_SECONDS", "15"))

    # Device metrics v1 is published every 60 s. Three missed intervals make the
    # values stale, but presence remains a separate backend/API decision.
    DEVICE_METRICS_STALE_SECONDS: int = int(os.getenv("DEVICE_METRICS_STALE_SECONDS", "180"))

    @property
    def database_url(self) -> str:
        # Pin the psycopg2 dialect explicitly: SQLAlchemy 2.1+ prefers the
        # psycopg3 (psycopg) driver by default for bare `postgresql://` URLs,
        # but this project pins psycopg2-binary (requirements.txt). Without
        # the explicit dialect, engine creation fails with
        # "No module named 'psycopg'" at import time.
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

settings = Settings()
