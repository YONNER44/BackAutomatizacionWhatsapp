from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from datetime import date
import os

from app.database.db import get_db
from app.models.price import Price
from app.models.provider import Provider
from app.services.excel import ExcelService
from app.services.sheets import SheetsService
from app.config import get_settings

router = APIRouter()
excel_svc = ExcelService()
sheets_svc = SheetsService()
settings = get_settings()


class PriceResponse(BaseModel):
    id: int
    medication_name: str
    price: float
    unit: str | None
    date_reported: date
    provider_id: int
    provider_name: str | None = None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[PriceResponse])
async def list_prices(
    db: AsyncSession = Depends(get_db),
    provider_id: int | None = Query(default=None),
    medication: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=100, le=500),
):
    query = (
        select(Price, Provider.name.label("provider_name"))
        .join(Provider, Price.provider_id == Provider.id, isouter=True)
        .order_by(Price.date_reported.desc(), Price.medication_name)
    )

    if provider_id:
        query = query.where(Price.provider_id == provider_id)
    if medication:
        query = query.where(Price.medication_name.ilike(f"%{medication}%"))
    if date_from:
        query = query.where(Price.date_reported >= date_from)
    if date_to:
        query = query.where(Price.date_reported <= date_to)

    query = query.limit(limit)
    result = await db.execute(query)
    rows = result.all()

    prices = []
    for row in rows:
        price = row[0]
        provider_name = row[1]
        prices.append(PriceResponse(
            id=price.id,
            medication_name=price.medication_name,
            price=price.price,
            unit=price.unit,
            date_reported=price.date_reported,
            provider_id=price.provider_id,
            provider_name=provider_name,
        ))
    return prices


@router.get("/summary")
async def get_summary(db: AsyncSession = Depends(get_db)):
    total_prices = await db.execute(select(func.count(Price.id)))
    total_medications = await db.execute(
        select(func.count(func.distinct(Price.medication_name)))
    )
    excel_summary = excel_svc.get_summary()

    return {
        "total_prices": total_prices.scalar(),
        "total_medications": total_medications.scalar(),
        "excel": excel_summary,
    }


@router.delete("/{price_id}")
async def delete_price(price_id: int, db: AsyncSession = Depends(get_db)):
    """Elimina un registro de precio por ID."""
    result = await db.execute(select(Price).where(Price.id == price_id))
    price = result.scalar_one_or_none()
    if not price:
        raise HTTPException(status_code=404, detail="Precio no encontrado")
    await db.delete(price)
    await db.commit()
    return {"success": True}


@router.post("/init-month")
async def init_monthly_sheet(
    db: AsyncSession = Depends(get_db),
    force: bool = Query(default=False, description="Si True, recrea la hoja aunque ya exista"),
):
    """
    Crea la hoja del mes actual en el Excel con el formato y los proveedores activos.
    Sin medicamentos — se agregan solos cuando lleguen precios por WhatsApp.
    Si la hoja ya existe y force=False, no hace nada (validación anti-duplicado).
    Si force=True, elimina y recrea la hoja con el nuevo formato.
    """
    current_month = date.today().strftime("%Y-%m")

    # Si Google Sheets está configurado, verificar ahí (es la fuente principal)
    # Si no, verificar el Excel local
    if settings.GOOGLE_SHEET_ID:
        already_exists = sheets_svc.monthly_sheet_exists()
    else:
        already_exists = excel_svc.monthly_sheet_exists()

    if already_exists and not force:
        return {
            "success": True,
            "created": False,
            "sheet": current_month,
            "message": f"La hoja '{current_month}' ya existe. No se realizó ningún cambio.",
        }

    providers_result = await db.execute(
        select(Provider).where(Provider.is_active == True).order_by(Provider.name)
    )
    providers = [p.name for p in providers_result.scalars().all()]

    # Crear en Excel local
    excel_svc.create_empty_monthly_sheet(providers, force=force)

    # Crear en Google Sheets (si está configurado)
    sheets_error = None
    if settings.GOOGLE_SHEET_ID:
        try:
            sheets_svc.create_empty_monthly_sheet(providers, force=force)
        except Exception as e:
            sheets_error = str(e)

    msg = f"Hoja '{current_month}' creada con {len(providers)} proveedor(es)."
    if sheets_error:
        msg += f" (Google Sheets: {sheets_error})"

    return {
        "success": True,
        "created": True,
        "sheet": current_month,
        "providers": len(providers),
        "message": msg,
    }


@router.post("/init-day")
async def init_day():
    """
    Inserta el bloque de encabezado del nuevo día (Arca software + Fecha/Medicamento/Precio/Cantidad)
    debajo de los datos existentes en el Excel y Google Sheets.
    El dueño agrega los medicamentos y fechas manualmente debajo del encabezado.
    """
    today = date.today()

    excel_result = excel_svc.create_day_header(today)

    sheets_result = {"created": False}
    sheets_error = None
    if settings.GOOGLE_SHEET_ID:
        try:
            sheets_result = sheets_svc.create_day_header(today)
        except Exception as e:
            sheets_error = str(e)

    created = excel_result["created"] or sheets_result["created"]
    msg = (
        f"Encabezado del día {today.strftime('%d/%m/%Y')} creado correctamente."
        if created
        else f"El día {today.strftime('%d/%m/%Y')} ya está inicializado."
    )
    if sheets_error:
        msg += f" (Google Sheets: {sheets_error})"

    return {
        "success": True,
        "created": created,
        "date": today.strftime("%d/%m/%Y"),
        "message": msg,
    }


@router.get("/export/excel")
async def export_excel(db: AsyncSession = Depends(get_db)):
    """Genera y descarga Excel desde la base de datos (mismo formato que Google Sheets)."""
    from fastapi.responses import Response

    result = await db.execute(
        select(Price, Provider.name.label("provider_name"))
        .join(Provider, Price.provider_id == Provider.id, isouter=True)
        .order_by(Price.date_reported, Price.medication_name)
    )
    rows = result.all()

    if not rows:
        raise HTTPException(status_code=404, detail="No hay datos para exportar")

    prices_data = [
        {
            "medication_name": row[0].medication_name,
            "price": row[0].price,
            "unit": row[0].unit,
            "provider_name": row[1] or f"Proveedor #{row[0].provider_id}",
            "date_reported": row[0].date_reported,
        }
        for row in rows
    ]

    excel_bytes = excel_svc.generate_report(prices_data)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=precios_medicamentos.xlsx"},
    )
