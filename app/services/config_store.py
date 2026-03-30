"""
Almacenamiento dinámico de configuración.
Lee/escribe un JSON en ./data/app_config.json.
Tiene prioridad sobre las variables de entorno (.env).
"""
import json
from pathlib import Path

CONFIG_PATH = Path("./data/app_config.json")


def get_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_config(updates: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    current = get_config()
    current.update(updates)
    CONFIG_PATH.write_text(
        json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def get_value(key: str, fallback: str = "") -> str:
    return get_config().get(key) or fallback
