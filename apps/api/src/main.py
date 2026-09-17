from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text
from src.database import engine
from src.routes.devices import router as devices_router
from src.services.mqtt_listener import start_mqtt_listener, stop_mqtt_listener

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: start listening to MQTT
    start_mqtt_listener()
    yield
    # Shutdown: stop MQTT listener
    stop_mqtt_listener()

app = FastAPI(
    title="Zero Touch Deployment (ZTD) Orchestrator",
    version="1.0.0",
    description="API for IoT device whitelisting, provisioning, and monitoring",
    lifespan=lifespan
)

# Include the device management router
app.include_router(devices_router)

@app.get("/", tags=["General"])
def root():
    return {"message": "ZTD Orchestrator API is running"}

@app.get("/health", tags=["General"])
def health_check():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status
    }
