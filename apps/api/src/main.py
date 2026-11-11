from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from src.database import engine
from src.routes.devices import router as devices_router
from src.routes.modules import router as modules_router
from src.services.mqtt_listener import start_mqtt_listener, stop_mqtt_listener
from src.routes.bootstrap import router as bootstrap_router
from src.provisioning.routes import router as provisioning_router

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the device management router
app.include_router(devices_router)
app.include_router(modules_router)
app.include_router(bootstrap_router)
app.include_router(provisioning_router)

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
