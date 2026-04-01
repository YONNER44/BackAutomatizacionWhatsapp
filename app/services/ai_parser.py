import json
import logging
from openai import AsyncOpenAI
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

SYSTEM_PROMPT = """Eres un asistente especializado en extraer listas de precios de medicamentos de mensajes de WhatsApp o imágenes de cotizaciones.

Reglas:
- Extrae solo medicamentos con precio
- El precio debe ser un número (float) sin formato, sin signos de moneda
- Si hay unidad de empaque (caja, frasco, tableta, inhalador, etc.), inclúyela en el campo "unit"
- Ignora encabezados, fechas, saludos y texto que no sea lista de precios
- Si no encuentras medicamentos con precio, devuelve lista vacía

Reglas de nombre:
- Primera letra en mayúscula, resto en minúscula
- Conserva dosis y presentación (ej: "Aspirina 500mg", "Dipirona 500mg")
- Si se proporciona una LISTA DE MEDICAMENTOS CONOCIDOS, usa SIEMPRE el nombre exacto de esa lista cuando el medicamento del mensaje corresponda a uno de ellos (aunque esté abreviado, tenga typos o variaciones). Ejemplo: si la lista tiene "Salbumed salbutamol 100 mcg" y el mensaje dice "salbum salbuta 100mcg", usa "Salbumed salbutamol 100 mcg"
- Si el medicamento del mensaje NO corresponde a ninguno de la lista, usa el nombre tal como aparece en el mensaje

Formato de respuesta (JSON):
{
  "items": [
    {
      "medication_name": "Nombre del medicamento",
      "price": 12500.0,
      "unit": "caja"
    }
  ]
}
"""


class AIParserService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL

    async def parse_prices(self, text: str, known_medications: list[str] = None) -> list[dict]:
        """
        Extrae medicamentos y precios del texto usando OpenAI o parser local.
        known_medications: lista de nombres canónicos del sheet para que la IA haga matching exacto.
        Retorna una lista de dicts con: medication_name, price, unit.
        """
        if not text or not text.strip():
            return []

        user_content = f"Extrae los medicamentos y precios del siguiente texto:\n\n{text}"
        if known_medications:
            med_list = "\n".join(f"- {m}" for m in known_medications)
            user_content += f"\n\nLISTA DE MEDICAMENTOS CONOCIDOS (usa estos nombres exactos cuando corresponda):\n{med_list}"

        # Intentar con OpenAI
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=2000,
            )
            content = response.choices[0].message.content
            data = json.loads(content)
            items = data.get("items", [])
            logger.info(f"AI Parser extrajo {len(items)} medicamentos")
            return items
        except Exception as e:
            logger.error(f"Error llamando a OpenAI, usando parser local: {e}")
            import re

            def parse_price(price_str: str) -> float:
                """Convierte precio en string al float correcto.
                Maneja separador de miles colombiano: 36.450 → 36450, 8.50 → 8.50"""
                clean = price_str.replace('*', '').strip()
                # Si termina en .XXX con exactamente 3 dígitos → miles (36.450 → 36450)
                if re.match(r'^\d+\.\d{3}$', clean):
                    return float(clean.replace('.', ''))
                # Si tiene coma → separador decimal europeo (12,75 → 12.75)
                clean = clean.replace(',', '.')
                return float(clean)

            items = []

            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                logger.info(f"Parser local revisando línea: {line}")

                # Patrón 1: precio con asteriscos al final → *36.450* o *$10.185*
                # Ej: "SERTRALINA 100 MG ... NOVAMED *36.450*"
                # Ej: "Zarzamas mas vital $10.500 -3% *$10.185*"
                m_asterisk = re.search(r'\*\$?(\d+[\.,]\d+)\*', line)
                if m_asterisk:
                    price_str = m_asterisk.group(1)
                    name_part = line[:m_asterisk.start()].strip()
                    # Quitar precio original + descuento al final (ej: "$10.500 -3%")
                    name_clean = re.sub(r'\s*\$[\d\.,]+\s*-?\d*%?\s*$', '', name_part)
                    # Quitar distribuidor (NOVAMED, LAFRANCOL, etc. al final)
                    name_clean = re.sub(r'\s+NOVAMED\b', '', name_clean, flags=re.IGNORECASE)
                    name_clean = name_clean.strip(' *$-')

                    # Extraer cantidad: "X 28 TAB", "X 10 CAPS", "X 100 COMP", etc.
                    unit = ""
                    m_unit = re.search(r'(X\s*\d+\s*(?:TAB|CAPS?|COMP|MG|ML|GR|UND|UNID|AMP|VIA|SOB)\w*)', name_clean, re.IGNORECASE)
                    if m_unit:
                        unit = m_unit.group(1).strip()
                        name_clean = name_clean[:m_unit.start()].strip()

                    if name_clean:
                        try:
                            items.append({
                                "medication_name": name_clean.strip(),
                                "price": parse_price(price_str),
                                "unit": unit,
                            })
                            continue
                        except ValueError:
                            pass

                # Patrón 2: "Nombre: $precio" o "Nombre $precio"
                # Ej: "Aspirina 500mg: $8.50", "Dipirona 500mg: $12.75"
                m_dollar = re.search(r'^(.+?)\s*[:\-]\s*\$\s*(\d+[\.,]\d+)', line)
                if m_dollar:
                    name_clean = m_dollar.group(1).strip()
                    try:
                        items.append({
                            "medication_name": name_clean,
                            "price": parse_price(m_dollar.group(2)),
                            "unit": None,
                        })
                        continue
                    except ValueError:
                        pass

            logger.info(f"Parser local extrajo {len(items)} medicamentos: {items}")
            return items
