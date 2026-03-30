import asyncio
import logging
from datetime import date

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database.db import init_db, AsyncSessionLocal
from app.routers import webhook, providers, prices, config

logger = logging.getLogger(__name__)

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
app.include_router(config.router, prefix="/config", tags=["Configuración"])


async def _try_init_monthly_sheet():
    """Intenta crear la hoja del mes actual en Excel y Google Sheets si no existe."""
    from sqlalchemy import select
    from app.models.provider import Provider
    from app.services.excel import ExcelService
    from app.services.sheets import SheetsService

    excel_svc = ExcelService()
    sheets_svc = SheetsService()
    sheet_label = date.today().strftime("%Y-%m")

    # Obtener proveedores activos
    async with AsyncSessionLocal() as db:
        providers_result = await db.execute(
            select(Provider).where(Provider.is_active == True).order_by(Provider.name)
        )
        prov_names = [p.name for p in providers_result.scalars().all()]

    # Excel local
    if not excel_svc.monthly_sheet_exists():
        created = excel_svc.create_empty_monthly_sheet(prov_names)
        if created:
            logger.info(f"Hoja Excel '{sheet_label}' creada automáticamente")

    # Google Sheets
    if not sheets_svc.monthly_sheet_exists():
        try:
            created = sheets_svc.create_empty_monthly_sheet(prov_names)
            if created:
                logger.info(f"Hoja Google Sheets '{sheet_label}' creada automáticamente")
        except Exception as e:
            logger.warning(f"No se pudo crear hoja en Google Sheets: {e}")


async def _monthly_sheet_watchdog():
    """Revisa cada hora si hay que crear la hoja del mes."""
    while True:
        try:
            await _try_init_monthly_sheet()
        except Exception as e:
            logger.error(f"Error en watchdog mensual: {e}")
        await asyncio.sleep(3600)  # verificar cada hora


@app.on_event("startup")
async def startup_event():
    await init_db()
    # Iniciar watchdog mensual en background
    asyncio.create_task(_monthly_sheet_watchdog())


@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy"}
