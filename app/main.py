from fastapi import FastAPI
from app.api.health import router as health_router
from app.api.sources import router as sources_router
from app.core.logging import setup_logging

app = FastAPI(title="Muratorium")

app.include_router(health_router)
app.include_router(sources_router)


@app.on_event("startup")
def on_startup() -> None:
    setup_logging()
