from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database.db import init_db
from app.routers import webhook, providers, prices

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="API para automatización de recolección de precios de medicamentos vía WhatsApp",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook.router, prefix="/api/webhook", tags=["WhatsApp Webhook"])
app.include_router(providers.router, prefix="/providers", tags=["Proveedores"])
app.include_router(prices.router, prefix="/prices", tags=["Precios"])


@app.on_event("startup")
async def startup_event():
    await init_db()


@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy"}
