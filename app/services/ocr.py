import base64
import logging
from openai import AsyncOpenAI
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class OCRService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def extract_text_from_bytes(self, image_bytes: bytes) -> str:
        """Extrae texto de una imagen usando OpenAI GPT-4o Vision."""
        try:
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Extrae TODO el texto visible en esta imagen exactamente como aparece, "
                                    "sin interpretarlo ni resumirlo. Incluye precios, nombres de medicamentos, "
                                    "cantidades y cualquier otro texto. Devuelve solo el texto extraído."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}",
                                    "detail": "high",
                                },
                            },
                        ],
                    }
                ],
                max_tokens=2000,
            )
            extracted = response.choices[0].message.content or ""
            logger.info(f"OCR extrajo {len(extracted)} caracteres de la imagen")
            return extracted

        except Exception as e:
            logger.error(f"Error en OCR: {e}")
            raise

    async def extract_text_from_url(self, image_url: str) -> str:
        """Extrae texto de una imagen por URL usando OpenAI GPT-4o Vision."""
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Extrae TODO el texto visible en esta imagen exactamente como aparece, "
                                    "sin interpretarlo ni resumirlo. Incluye precios, nombres de medicamentos, "
                                    "cantidades y cualquier otro texto. Devuelve solo el texto extraído."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": image_url, "detail": "high"},
                            },
                        ],
                    }
                ],
                max_tokens=2000,
            )
            extracted = response.choices[0].message.content or ""
            logger.info(f"OCR por URL extrajo {len(extracted)} caracteres")
            return extracted

        except Exception as e:
            logger.error(f"Error en OCR por URL: {e}")
            raise
