import json
import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.services.config_store import get_config, save_config, get_value
from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


@router.get("/status")
async def get_config_status():
    """Retorna el estado actual de la configuración de Google Sheets."""
    config = get_config()
    sheet_id = config.get("GOOGLE_SHEET_ID") or settings.GOOGLE_SHEET_ID or ""
    has_credentials = bool(
        config.get("GOOGLE_CREDENTIALS_JSON")
        or (
            settings.GOOGLE_APPLICATION_CREDENTIALS
            and __import__("pathlib").Path(settings.GOOGLE_APPLICATION_CREDENTIALS).exists()
        )
    )

    connected = False
    error = None
    account_email = None

    if sheet_id and has_credentials:
        try:
            from app.services.sheets import SheetsService
            svc = SheetsService()
            svc.invalidate_cache()
            sp = svc._get_spreadsheet()
            connected = True
            # Email de la cuenta de servicio
            creds_str = config.get("GOOGLE_CREDENTIALS_JSON")
            if creds_str:
                account_email = json.loads(creds_str).get("client_email", "")
            elif settings.GOOGLE_APPLICATION_CREDENTIALS:
                import pathlib
                p = pathlib.Path(settings.GOOGLE_APPLICATION_CREDENTIALS)
                if p.exists():
                    account_email = json.loads(p.read_text()).get("client_email", "")
        except Exception as e:
            error = str(e)

    return {
        "sheet_id": sheet_id,
        "has_credentials": has_credentials,
        "account_email": account_email,
        "connected": connected,
        "error": error,
    }


@router.post("/google")
async def save_google_config(
    sheet_id: str = Form(...),
    credentials: UploadFile = File(None),
):
    """
    Guarda la configuración de Google Sheets:
    - sheet_id: ID de la Google Sheet del cliente
    - credentials: archivo JSON de la cuenta de servicio (opcional si ya hay uno guardado)
    """
    updates = {"GOOGLE_SHEET_ID": sheet_id.strip()}

    if credentials and credentials.filename:
        content = await credentials.read()
        try:
            creds_json = json.loads(content)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="El archivo no es un JSON válido.")

        if creds_json.get("type") != "service_account":
            raise HTTPException(
                status_code=400,
                detail="El archivo debe ser una cuenta de servicio de Google (type: service_account).",
            )

        updates["GOOGLE_CREDENTIALS_JSON"] = content.decode("utf-8")

    save_config(updates)

    # Invalidar caché del servicio para que use las nuevas credenciales
    try:
        from app.services.sheets import SheetsService
        svc = SheetsService()
        svc.invalidate_cache()
    except Exception:
        pass

    # Verificar conexión
    try:
        from app.services.sheets import SheetsService
        svc = SheetsService()
        svc._get_spreadsheet()
        return {"success": True, "message": "Configuración guardada y conexión verificada correctamente."}
    except Exception as e:
        return {
            "success": False,
            "message": f"Configuración guardada, pero la conexión falló: {e}",
        }
