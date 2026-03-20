from fastapi import APIRouter, Depends, HTTPException
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, text
from pydantic import BaseModel

from app.database.db import get_db
from app.models.provider import Provider


logger = logging.getLogger(__name__)

router = APIRouter()


class ProviderCreate(BaseModel):
    phone_number: str
    name: str


class ProviderUpdate(BaseModel):
    name: str | None = None
    phone_number: str | None = None
    is_active: bool | None = None


class ProviderResponse(BaseModel):
    id: int
    phone_number: str
    name: str
    is_active: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=list[ProviderResponse])
async def list_providers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Provider).order_by(Provider.name))
    return result.scalars().all()


@router.post("", response_model=ProviderResponse, status_code=201)
async def create_provider(data: ProviderCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(Provider).where(Provider.phone_number == data.phone_number)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="El número de teléfono ya está registrado")

    provider = Provider(phone_number=data.phone_number, name=data.name)
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return provider


@router.get("/{provider_id}", response_model=ProviderResponse)
async def get_provider(provider_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    return provider


@router.put("/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: int, data: ProviderUpdate, db: AsyncSession = Depends(get_db)
):
    # Fetch current using raw SQL to bypass ORM identity map
    row = (await db.execute(
        text("SELECT id, name, phone_number, is_active FROM providers WHERE id = :id"),
        {"id": provider_id}
    )).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    current_id, current_name, current_phone, current_active = row

    new_name = data.name if data.name is not None else current_name
    new_phone = data.phone_number if data.phone_number is not None else current_phone
    new_active = data.is_active if data.is_active is not None else bool(current_active)

    # Check duplicate phone only if it changed
    if new_phone != current_phone:
        dup = (await db.execute(
            text("SELECT id FROM providers WHERE phone_number = :phone AND id != :id"),
            {"phone": new_phone, "id": provider_id}
        )).fetchone()
        if dup:
            raise HTTPException(status_code=400, detail="El número de teléfono ya está registrado en otro proveedor")

    # Raw SQL update — no ORM involved
    await db.execute(
        text("UPDATE providers SET name = :name, phone_number = :phone, is_active = :active WHERE id = :id"),
        {"name": new_name, "phone": new_phone, "active": new_active, "id": provider_id}
    )
    await db.commit()

    return ProviderResponse(id=current_id, name=new_name, phone_number=new_phone, is_active=new_active)


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(provider_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    await db.delete(provider)
    await db.commit()
