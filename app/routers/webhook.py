import base64
import logging
from datetime import date, datetime
from fastapi import APIRouter, Request, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.db import get_db
from app.models.provider import Provider
from app.models.message import Message, MessageType, MessageStatus
from app.models.price import Price
from app.services.ocr import OCRService
from app.services.ai_parser import AIParserService
from app.services.excel import ExcelService
from app.services.sheets import SheetsService
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

ocr_svc = OCRService()
ai_parser_svc = AIParserService()
excel_svc = ExcelService()
sheets_svc = SheetsService()


@router.post("/whatsapp-web")
async def receive_message_whatsapp_web(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Recibe mensajes desde el servicio whatsapp-web.js."""
    payload = await request.json()
    logger.info(f"Mensaje de WhatsApp Web recibido desde: {payload.get('from')}")

    raw_from = payload.get("from", "")
    phone_number = raw_from.replace("@c.us", "").replace("@lid", "").replace("@s.whatsapp.net", "")
    message_type = payload.get("type", "")
    message_body = payload.get("body", "")
    has_media = payload.get("hasMedia", False)
    timestamp = payload.get("timestamp", 0)

    if message_type == "chat":
        message_type = "text"
    elif message_type in ["image", "ptt", "video", "document"]:
        message_type = "image" if message_type == "image" else "text"

    full_phone = phone_number
    local_phone = full_phone[-10:] if len(full_phone) > 10 else full_phone

    result = await db.execute(
        select(Provider).where(Provider.phone_number.in_([full_phone, local_phone]))
    )
    provider = result.scalar_one_or_none()

    wa_message_id = payload.get("messageId") or f"web_{timestamp}_{phone_number}"

    message = Message(
        whatsapp_message_id=wa_message_id,
        provider_id=provider.id if provider else None,
        phone_number=phone_number,
        message_type=MessageType(message_type) if message_type in ["text", "image"] else None,
        raw_text=message_body if not has_media else None,
        status=MessageStatus.RECEIVED,
    )

    if message.message_type is None:
        logger.info(f"Tipo de mensaje no soportado: {message_type}")
        return {"status": "unsupported_type"}

    existing_msg = await db.execute(
        select(Message).where(Message.whatsapp_message_id == wa_message_id)
    )
    if existing_msg.scalar_one_or_none():
        logger.info(f"Mensaje duplicado ignorado: {wa_message_id}")
        return {"status": "duplicate", "success": True}

    db.add(message)
    await db.flush()

    msg_data = {
        "whatsapp_message_id": message.whatsapp_message_id,
        "phone_number": phone_number,
        "message_type": message_type,
        "raw_text": message_body,
        "media_base64": None,
        "media_mimetype": None,
    }

    if has_media and payload.get("media"):
        media = payload.get("media", {})
        msg_data["media_base64"] = media.get("data")
        msg_data["media_mimetype"] = media.get("mimetype")

    if provider:
        background_tasks.add_task(process_message, message.id, msg_data, provider)
    else:
        logger.warning(f"Mensaje de proveedor desconocido: {phone_number}")

    await db.commit()
    return {"success": True, "status": "received"}


async def process_message(message_id: int, msg_data: dict, provider: Provider):
    """Tarea en background: extrae precios del mensaje y actualiza Excel/Sheets."""
    from app.database.db import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(Message).where(Message.id == message_id))
            message = result.scalar_one()
            message.status = MessageStatus.PROCESSING

            text_to_parse = ""

            if msg_data["message_type"] == "text":
                text_to_parse = msg_data.get("raw_text", "")

            elif msg_data["message_type"] == "image" and msg_data.get("media_base64"):
                image_bytes = base64.b64decode(msg_data["media_base64"])
                text_to_parse = await ocr_svc.extract_text_from_bytes(image_bytes)
                message.extracted_text = text_to_parse

            if not text_to_parse:
                logger.warning(f"No hay texto para procesar en mensaje {message_id}")
                message.status = MessageStatus.FAILED
                message.error_message = "No se pudo extraer texto del mensaje"
                await db.commit()
                return

            prices_data = await ai_parser_svc.parse_prices(text_to_parse)

            today = date.today()
            for item in prices_data:
                med_name = item["medication_name"]
                existing_result = await db.execute(
                    select(Price).where(
                        Price.provider_id == provider.id,
                        Price.medication_name == med_name,
                    )
                )
                existing_price = existing_result.scalar_one_or_none()
                if existing_price:
                    existing_price.price = item["price"]
                    existing_price.date_reported = today
                    if item.get("unit"):
                        existing_price.unit = item["unit"]
                else:
                    db.add(Price(
                        message_id=message.id,
                        provider_id=provider.id,
                        medication_name=med_name,
                        price=item["price"],
                        unit=item.get("unit"),
                        date_reported=today,
                    ))

            excel_svc.update_prices(provider.name, prices_data, today)

            if settings.GOOGLE_SHEET_ID:
                try:
                    sheets_svc.update_prices(provider.name, prices_data, today)
                except Exception as sheets_err:
                    logger.warning(f"Google Sheets no se actualizó: {sheets_err}")

            message.status = MessageStatus.PROCESSED
            message.processed_at = datetime.utcnow()
            await db.commit()

            logger.info(f"Mensaje {message_id} procesado: {len(prices_data)} precios de '{provider.name}'")

        except Exception as e:
            logger.error(f"Error procesando mensaje {message_id}: {e}")
            try:
                message.status = MessageStatus.FAILED
                message.error_message = str(e)
                await db.commit()
            except Exception:
                pass
