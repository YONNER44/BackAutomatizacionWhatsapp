import logging
from datetime import date
import gspread
from google.oauth2.service_account import Credentials
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

PROVIDER_HEADER_STYLE = {
    "backgroundColor": {"red": 0.18, "green": 0.46, "blue": 0.71},
    "textFormat": {"bold": True, "fontSize": 11, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
    "horizontalAlignment": "CENTER",
    "verticalAlignment": "MIDDLE",
}

COL_HEADER_STYLE = {
    "backgroundColor": {"red": 0.18, "green": 0.46, "blue": 0.71},
    "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
    "horizontalAlignment": "CENTER",
    "verticalAlignment": "MIDDLE",
}

GREEN_STYLE = {
    "backgroundColor": {"red": 0.776, "green": 0.937, "blue": 0.804},
    "textFormat": {"bold": True, "foregroundColor": {"red": 0.153, "green": 0.384, "blue": 0.129}},
}

NO_STYLE = {
    "backgroundColor": {"red": 1, "green": 1, "blue": 1},
    "textFormat": {"bold": False, "foregroundColor": {"red": 0, "green": 0, "blue": 0}},
}

NUMBER_FORMAT_STYLE = {
    "numberFormat": {"type": "NUMBER", "pattern": "#,##0.##"},
}

# Filas fijas de la estructura
PROVIDER_ROW = 1     # Fila 1: nombres de proveedores (empiezan en col C)
COL_HEADER_ROW = 2   # Fila 2: "Fecha" | "Medicamento" | "Precio" | "Cantidad" | "Precio" | "Cantidad" ...
DATA_START_ROW = 3   # Fila 3 en adelante: datos

# Columnas compartidas (fijas para todos los proveedores)
FECHA_COL = 1        # Col A
MED_COL = 2          # Col B
FIRST_PROVIDER_COL = 3  # Col C: primer proveedor (Precio), D: Cantidad, E: siguiente Precio, etc.


class SheetsService:
    def __init__(self):
        self._client = None
        self._spreadsheet = None

    def _get_sheet_id(self) -> str:
        from app.services.config_store import get_value
        return get_value("GOOGLE_SHEET_ID", settings.GOOGLE_SHEET_ID or "")

    def _get_credentials(self):
        import json as _json
        from app.services.config_store import get_config
        config = get_config()
        creds_str = config.get("GOOGLE_CREDENTIALS_JSON")
        if creds_str:
            return Credentials.from_service_account_info(
                _json.loads(creds_str), scopes=SCOPES
            )
        if settings.GOOGLE_APPLICATION_CREDENTIALS:
            from pathlib import Path
            if Path(settings.GOOGLE_APPLICATION_CREDENTIALS).exists():
                return Credentials.from_service_account_file(
                    settings.GOOGLE_APPLICATION_CREDENTIALS, scopes=SCOPES
                )
        raise ValueError("No hay credenciales de Google configuradas. Ve a Configuración para agregarlas.")

    def invalidate_cache(self):
        self._client = None
        self._spreadsheet = None

    def _get_spreadsheet(self):
        if self._spreadsheet is not None:
            return self._spreadsheet

        sheet_id = self._get_sheet_id()
        if not sheet_id:
            raise ValueError("Falta GOOGLE_SHEET_ID. Configúralo en la página de Configuración.")

        creds = self._get_credentials()
        self._client = gspread.authorize(creds)
        self._spreadsheet = self._client.open_by_key(sheet_id)
        return self._spreadsheet

    def _get_or_create_monthly_sheet(self, spreadsheet, sheet_name: str):
        """Obtiene o crea la hoja mensual (ej: '2026-03'). Se crea vacía sin formato."""
        try:
            return spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(title=sheet_name, rows=500, cols=50)
            return ws

    def _get_or_create_provider_col(self, sheet, provider_name: str) -> int:
        """
        Busca o crea la columna de precio del proveedor.

        Estructura:
          - Col A: Fecha (compartida)
          - Col B: Medicamento (compartida)
          - Col C+: Proveedores (Precio + Cantidad, 2 cols cada uno)

        Retorna índice de columna de Precio (1-based).
        """
        from gspread.utils import rowcol_to_a1

        # Usar fila 2 (encabezados) para encontrar columnas "Precio" existentes.
        # Es más confiable que fila 1 que tiene celdas combinadas y gspread
        # recorta los valores vacíos al final, lo que hace que len() sea incorrecto.
        header_row = sheet.row_values(COL_HEADER_ROW)
        existing_price_cols = [
            i + 1 for i, v in enumerate(header_row)
            if v == "Precio" and i + 1 >= FIRST_PROVIDER_COL
        ]

        # Leer fila 1 para verificar nombres de proveedores existentes
        try:
            row1_data = sheet.get("A1:ZZ1")
            row1_values = row1_data[0] if row1_data else []
        except Exception:
            row1_values = sheet.row_values(PROVIDER_ROW)

        # Verificar si el proveedor ya existe
        for price_col in existing_price_cols:
            # Primer proveedor: nombre guardado en A1 (índice 0)
            # Siguientes: nombre guardado en su columna de precio
            check_idx = 0 if price_col == FIRST_PROVIDER_COL else price_col - 1
            if check_idx < len(row1_values) and row1_values[check_idx] == provider_name:
                return price_col

        # Nuevo proveedor: columna siguiente a la última existente
        if existing_price_cols:
            new_price_col = max(existing_price_cols) + 2
        else:
            new_price_col = FIRST_PROVIDER_COL

        new_unit_col = new_price_col + 1

        price_cell_row1 = rowcol_to_a1(PROVIDER_ROW, new_price_col)
        unit_cell_row1 = rowcol_to_a1(PROVIDER_ROW, new_unit_col)
        price_header_cell = rowcol_to_a1(COL_HEADER_ROW, new_price_col)
        unit_header_cell = rowcol_to_a1(COL_HEADER_ROW, new_unit_col)

        # Fila 1: nombre del proveedor
        # Primer proveedor: combina A1:D1 (Fecha+Medicamento+Precio+Cantidad)
        # Siguientes: solo sus 2 columnas (Precio+Cantidad)
        if new_price_col == FIRST_PROVIDER_COL:
            merge_start = "A1"
        else:
            merge_start = price_cell_row1

        sheet.update(merge_start, [[provider_name]])
        try:
            sheet.merge_cells(f"{merge_start}:{unit_cell_row1}")
        except Exception as e:
            logger.warning(f"No se pudo combinar {merge_start}:{unit_cell_row1}: {e}")
        sheet.format(f"{merge_start}:{unit_cell_row1}", PROVIDER_HEADER_STYLE)

        # Fila 2: sub-encabezados Precio y Cantidad
        sheet.update(price_header_cell, [["Precio"]])
        sheet.format(price_header_cell, COL_HEADER_STYLE)
        sheet.update(unit_header_cell, [["Cantidad"]])
        sheet.format(unit_header_cell, COL_HEADER_STYLE)

        return new_price_col

    def _get_med_row_map(self, sheet, all_values: list = None) -> dict:
        """
        Lee medicamentos (col B desde DATA_START_ROW) y retorna {nombre_lower: row_idx}.
        Si se pasa all_values (resultado de get_all_values), lo reutiliza sin llamada extra.
        En caso de medicamentos repetidos en distintos días, conserva la ÚLTIMA fila.
        """
        if all_values is None:
            col_b = sheet.col_values(MED_COL)
            med_map = {}
            for idx, val in enumerate(col_b[DATA_START_ROW - 1:], start=DATA_START_ROW):
                if val:
                    med_map[val.lower()] = idx
            return med_map

        med_map = {}
        for idx, row in enumerate(all_values[DATA_START_ROW - 1:], start=DATA_START_ROW):
            if len(row) >= MED_COL and row[MED_COL - 1]:
                med_map[row[MED_COL - 1].lower()] = idx
        return med_map

    def _get_med_row_map_by_date(self, all_values: list, date_str: str) -> dict:
        """
        Retorna {nombre_lower: row_idx} SOLO para filas donde Col A == date_str (hoy).
        Permite actualizar únicamente el día en curso sin tocar días anteriores.
        """
        med_map = {}
        for idx, row in enumerate(all_values[DATA_START_ROW - 1:], start=DATA_START_ROW):
            if len(row) >= MED_COL and row[MED_COL - 1]:
                row_date = row[FECHA_COL - 1].replace(" ", "") if len(row) >= FECHA_COL else ""
                if row_date == date_str:
                    med_map[row[MED_COL - 1].lower()] = idx
        return med_map

    @staticmethod
    def _normalize_med_name(name: str) -> str:
        """
        Normaliza nombre de medicamento para comparación:
        - Quita paréntesis y su contenido: "Tinox (RG)" → "Tinox RG"
        - Quita sufijos de empaque: "CAJA X 30 UNDS", "FRASCO 500 ML", etc.
        - Colapsa espacios
        """
        import re
        # Quitar paréntesis pero conservar el contenido: "(RG)" → "RG"
        name = re.sub(r'\(([^)]*)\)', r'\1', name)
        # Quitar sufijos de empaque comunes al final
        name = re.sub(
            r'\s+(FRASCO|CAJA|TABLETAS?|TABS?|CAPS?|COMP|AMP|SOB|UND[S]?|UNID|ML|MG|GR|MCG)'
            r'(\s+\d+.*)?$', '', name, flags=re.IGNORECASE
        )
        return re.sub(r'\s+', ' ', name).strip().lower()

    def _find_med_key(self, med_row_map: dict, search_key: str) -> str | None:
        """
        Busca medicamento con coincidencia flexible (4 niveles):
        1. Exacto (case-insensitive)
        2. Subset de palabras
        3. Nombres normalizados (sin paréntesis ni sufijos de empaque)
        4. Similitud fuzzy (umbral 80%)
        """
        from difflib import SequenceMatcher

        # 1. Exacto
        if search_key in med_row_map:
            return search_key

        # 2. Subset de palabras
        search_words = set(search_key.split())
        best_word_match = None
        best_overlap = 0
        for existing_key in med_row_map:
            existing_words = set(existing_key.split())
            if search_words.issubset(existing_words) or existing_words.issubset(search_words):
                overlap = len(search_words & existing_words)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_word_match = existing_key
        if best_word_match:
            return best_word_match

        # 3. Comparación con nombres normalizados (quita paréntesis y sufijos de empaque)
        norm_search = self._normalize_med_name(search_key)
        norm_search_words = set(norm_search.split())
        for existing_key in med_row_map:
            norm_existing = self._normalize_med_name(existing_key)
            norm_existing_words = set(norm_existing.split())
            if (norm_search == norm_existing or
                    norm_search_words.issubset(norm_existing_words) or
                    norm_existing_words.issubset(norm_search_words)):
                logger.info(f"Coincidencia normalizada: '{search_key}' → '{existing_key}'")
                return existing_key

        # 4. Similitud fuzzy sobre nombres normalizados (maneja typos)
        THRESHOLD = 0.80
        best_match = None
        best_ratio = 0.0
        for existing_key in med_row_map:
            norm_existing = self._normalize_med_name(existing_key)
            ratio = SequenceMatcher(None, norm_search, norm_existing).ratio()
            if ratio >= THRESHOLD and ratio > best_ratio:
                best_ratio = ratio
                best_match = existing_key

        if best_match:
            logger.info(f"Coincidencia fuzzy: '{search_key}' → '{best_match}' ({best_ratio:.0%})")
        return best_match

    def _mark_best_prices(self, sheet, price_cols: list[int], all_data: list):
        """
        Marca en verde el precio más bajo de cada fila de datos entre todos los proveedores.
        Itera TODAS las filas de datos (incluyendo múltiples días) en lugar de un mapa
        deduplicado, para que cada día tenga su propio marcado correcto.
        """
        from gspread.utils import rowcol_to_a1

        if not price_cols or not all_data:
            return

        for idx, row in enumerate(all_data[DATA_START_ROW - 1:], start=DATA_START_ROW):
            if len(row) < MED_COL or not row[MED_COL - 1]:
                continue

            prices = []
            for col in price_cols:
                if col - 1 < len(row):
                    try:
                        val_str = str(row[col - 1]).strip()
                        if not val_str:
                            continue
                        val_str = val_str.replace(',', '').rstrip('.')
                        val = float(val_str)
                        if val > 0:
                            prices.append((col, val))
                    except (ValueError, TypeError):
                        pass

            if len(prices) < 2:
                for col, _ in prices:
                    try:
                        sheet.format(rowcol_to_a1(idx, col), NO_STYLE)
                    except Exception:
                        pass
                continue

            min_price = min(v for _, v in prices)
            all_equal = all(v == min_price for _, v in prices)

            for col, val in prices:
                cell = rowcol_to_a1(idx, col)
                style = GREEN_STYLE if (val == min_price and not all_equal) else NO_STYLE
                try:
                    sheet.format(cell, style)
                except Exception as e:
                    logger.warning(f"Error formateando {cell}: {e}")

    def update_prices(self, provider_name: str, prices: list[dict], report_date: date = None) -> str:
        """
        Actualiza Google Sheets con los precios del proveedor.
        Estructura:
          Col A: Fecha (compartida)
          Col B: Medicamento (compartida)
          Col C+: Precio | Cantidad por proveedor (2 cols cada uno)
        """
        if not prices:
            logger.info(f"No hay precios para actualizar de '{provider_name}'")
            return self.get_sheet_url()

        report_date = report_date or date.today()
        sheet_name = report_date.strftime("%Y-%m")
        date_str = report_date.strftime("%d/%m/%Y")

        try:
            spreadsheet = self._get_spreadsheet()
            sheet = self._get_or_create_monthly_sheet(spreadsheet, sheet_name)

            from gspread.utils import rowcol_to_a1

            # Detectar si el proveedor es nuevo (antes de crear su columna)
            header_row_before = sheet.row_values(COL_HEADER_ROW)
            existing_price_cols = [
                i + 1 for i, v in enumerate(header_row_before)
                if v == "Precio" and i + 1 >= FIRST_PROVIDER_COL
            ]

            provider_price_col = self._get_or_create_provider_col(sheet, provider_name)
            provider_unit_col = provider_price_col + 1
            is_new_provider = provider_price_col not in existing_price_cols

            # Obtener todos los datos una sola vez para minimizar llamadas a la API
            all_current_data = sheet.get_all_values()

            # Mapa de TODOS los medicamentos en la hoja (cualquier fecha) — para validar
            all_med_map = self._get_med_row_map(sheet, all_current_data)

            # Mapa SOLO de los medicamentos de HOY — solo estos se actualizan
            today_med_map = self._get_med_row_map_by_date(all_current_data, date_str)

            # Si el proveedor es nuevo, llenar con "NO" solo las filas de HOY
            if is_new_provider and today_med_map:
                no_updates = []
                for _, row_idx in today_med_map.items():
                    no_updates.append({
                        "range": rowcol_to_a1(row_idx, provider_price_col),
                        "values": [["NO"]],
                    })
                    no_updates.append({
                        "range": rowcol_to_a1(row_idx, provider_unit_col),
                        "values": [["NO"]],
                    })
                if no_updates:
                    sheet.batch_update(no_updates)

            # Siguiente fila disponible = después de todos los datos existentes
            next_available_row = (max(all_med_map.values()) + 1) if all_med_map else DATA_START_ROW

            batch_updates = []
            updated_keys = set()

            for item in prices:
                med_name = item.get("medication_name", "").strip()
                price_val = item.get("price")
                unit_val = item.get("unit") or ""

                if not med_name or price_val is None:
                    continue

                key = med_name.lower()

                # 1. Buscar en las filas de HOY primero
                matched_key = self._find_med_key(today_med_map, key)

                if matched_key is None:
                    # Medicamento no está en las filas de hoy → ignorar completamente.
                    # Solo se actualiza lo que el admin ya inicializó para este día.
                    logger.info(
                        f"Sheets: '{med_name}' no está en las filas de hoy ({date_str}), se ignora"
                    )
                    continue

                updated_keys.add(matched_key)
                row_idx = today_med_map[matched_key]

                # Actualizar precio y cantidad en la fila de hoy
                batch_updates.append({
                    "range": rowcol_to_a1(row_idx, FECHA_COL),
                    "values": [[date_str]],
                })
                batch_updates.append({
                    "range": rowcol_to_a1(row_idx, provider_price_col),
                    "values": [[price_val]],
                })
                batch_updates.append({
                    "range": rowcol_to_a1(row_idx, provider_unit_col),
                    "values": [[unit_val if unit_val else "NO"]],
                })

            # Medicamentos de HOY que este proveedor NO incluyó:
            # poner "NO" solo si la celda está vacía (no sobreescribir otra respuesta)
            for existing_key, row_idx in today_med_map.items():
                if existing_key not in updated_keys and not any(
                    existing_key == uk or set(existing_key.split()).issubset(set(uk.split())) or set(uk.split()).issubset(set(existing_key.split()))
                    for uk in updated_keys
                ):
                    row_data = all_current_data[row_idx - 1] if row_idx - 1 < len(all_current_data) else []
                    current_price = row_data[provider_price_col - 1] if provider_price_col - 1 < len(row_data) else ""
                    current_unit = row_data[provider_unit_col - 1] if provider_unit_col - 1 < len(row_data) else ""
                    if not current_price:
                        batch_updates.append({
                            "range": rowcol_to_a1(row_idx, provider_price_col),
                            "values": [["NO"]],
                        })
                    if not current_unit:
                        batch_updates.append({
                            "range": rowcol_to_a1(row_idx, provider_unit_col),
                            "values": [["NO"]],
                        })

            if batch_updates:
                sheet.batch_update(batch_updates)

            # Formatear columna de precios con separador de miles
            last_data_row = next_available_row - 1
            if last_data_row >= DATA_START_ROW:
                price_range = f"{rowcol_to_a1(DATA_START_ROW, provider_price_col)}:{rowcol_to_a1(last_data_row, provider_price_col)}"
                try:
                    sheet.format(price_range, NUMBER_FORMAT_STYLE)
                except Exception as e:
                    logger.warning(f"No se pudo formatear columna de precios: {e}")

            # Marcar mejor precio en verde — usando todos los datos actualizados
            updated_all_data = sheet.get_all_values()
            header_row = updated_all_data[COL_HEADER_ROW - 1] if len(updated_all_data) >= COL_HEADER_ROW else []
            all_price_cols = [i + 1 for i, v in enumerate(header_row) if v == "Precio"]
            self._mark_best_prices(sheet, all_price_cols, updated_all_data)

            logger.info(f"Sheets actualizado: hoja '{sheet_name}', '{provider_name}', {len(prices)} precios")
            return self.get_sheet_url()

        except Exception as e:
            logger.error(f"Error actualizando Google Sheets: {e}")
            raise

    def monthly_sheet_exists(self, target_date: date = None) -> bool:
        """Verifica si ya existe la hoja del mes en Google Sheets."""
        if not self._get_sheet_id():
            return False
        target_date = target_date or date.today()
        sheet_name = target_date.strftime("%Y-%m")
        try:
            spreadsheet = self._get_spreadsheet()
            all_sheets = [ws.title for ws in spreadsheet.worksheets()]
            return sheet_name in all_sheets
        except Exception as e:
            logger.warning(f"No se pudo verificar hoja en Sheets: {e}")
            return False

    def create_empty_monthly_sheet(
        self,
        provider_names: list[str],
        target_date: date = None,
        force: bool = False,
    ) -> bool:
        """
        Crea la hoja del mes en Google Sheets como pestaña vacía (sin formato ni encabezados).
        El formato se crea cuando el usuario pulsa "Inicializar día".
        Si force=True elimina la hoja existente y la recrea vacía.
        Retorna True si se creó, False si ya existía (y no se forzó).
        """
        if not self._get_sheet_id():
            logger.info("GOOGLE_SHEET_ID no configurado, se omite creación en Sheets")
            return False

        target_date = target_date or date.today()
        sheet_name = target_date.strftime("%Y-%m")

        try:
            spreadsheet = self._get_spreadsheet()
            all_sheet_titles = [ws.title for ws in spreadsheet.worksheets()]

            if sheet_name in all_sheet_titles:
                if not force:
                    logger.info(f"Hoja Sheets '{sheet_name}' ya existe, no se sobreescribe")
                    return False
                # Eliminar la hoja para recrearla limpia
                existing = spreadsheet.worksheet(sheet_name)
                spreadsheet.del_worksheet(existing)
                logger.info(f"Hoja Sheets '{sheet_name}' eliminada para recrear")

            # Crear hoja nueva vacía — el formato se aplica en create_day_header
            spreadsheet.add_worksheet(title=sheet_name, rows=500, cols=50)
            logger.info(f"Hoja Sheets '{sheet_name}' creada (vacía, sin formato)")
            return True

        except Exception as e:
            logger.error(f"Error creando hoja mensual en Sheets: {e}")
            raise

    def create_day_header(
        self, target_date: date = None, provider_names: list[str] | None = None
    ) -> dict:
        """
        Inserta el bloque de encabezado del nuevo día en Google Sheets.
        Si la hoja está vacía (primer día del mes), crea la estructura completa
        (filas 1-2 con proveedores y sub-encabezados) usando provider_names.
        Para días posteriores añade un nuevo bloque debajo de los datos existentes.
        Retorna {"created": bool}.
        """
        if not self._get_sheet_id():
            return {"created": False}

        target_date = target_date or date.today()
        sheet_name = target_date.strftime("%Y-%m")

        try:
            spreadsheet = self._get_spreadsheet()
            sheet = self._get_or_create_monthly_sheet(spreadsheet, sheet_name)

            from gspread.utils import rowcol_to_a1

            all_values = sheet.get_all_values()
            date_str = target_date.strftime("%d/%m/%Y")
            MARKER_COL = 26  # Columna Z — invisible para el usuario

            # Buscar marcador desde COL_HEADER_ROW (fila 2) para cubrir también el primer día
            for idx, row in enumerate(all_values[COL_HEADER_ROW - 1:], start=COL_HEADER_ROW):
                if len(row) >= MARKER_COL and row[MARKER_COL - 1] == date_str:
                    if row[MED_COL - 1].strip():
                        logger.info(f"Sheets: encabezado del día {date_str} ya existe, no se duplica")
                        return {"created": False}
                    # Marcador huérfano → limpiar y permitir reinicialización
                    logger.info(f"Sheets: marcador huérfano en fila {idx}, limpiando y recreando")
                    sheet.update(values=[[""]], range_name=rowcol_to_a1(idx, MARKER_COL))

            # Detectar si la hoja está vacía (sin estructura de proveedores)
            col_headers = all_values[COL_HEADER_ROW - 1] if len(all_values) >= COL_HEADER_ROW else []
            price_cols = [
                i + 1 for i, v in enumerate(col_headers)
                if v == "Precio" and i + 1 >= FIRST_PROVIDER_COL
            ]
            is_blank = not price_cols

            if is_blank:
                # Primer día del mes: crear estructura inicial (filas 1-2) con los proveedores
                if not provider_names:
                    logger.warning("Sheets: hoja vacía pero no se proporcionaron proveedores")
                    return {"created": False}
                # Fila 2: encabezados fijos Fecha y Medicamento (cols A y B)
                sheet.update(f"A{COL_HEADER_ROW}:B{COL_HEADER_ROW}", [["Fecha", "Medicamento"]])
                sheet.format(f"A{COL_HEADER_ROW}", COL_HEADER_STYLE)
                sheet.format(f"B{COL_HEADER_ROW}", COL_HEADER_STYLE)
                for prov_name in provider_names:
                    self._get_or_create_provider_col(sheet, prov_name)
                # Marcador en col Z de COL_HEADER_ROW (fila 2)
                sheet.update(values=[[date_str]], range_name=rowcol_to_a1(COL_HEADER_ROW, MARKER_COL))
                logger.info(
                    f"Sheets: estructura inicial del mes creada con {len(provider_names)} proveedor(es)"
                )
                return {"created": True}

            # Día posterior: añadir nuevo bloque debajo de los datos existentes
            all_med_map = self._get_med_row_map(sheet, all_values)
            last_data_row = max(all_med_map.values()) if all_med_map else DATA_START_ROW - 1
            prov_header_row = last_data_row + 2
            col_header_row = prov_header_row + 1

            prov_row_values = all_values[PROVIDER_ROW - 1] if len(all_values) >= PROVIDER_ROW else []

            batch_updates = []
            last_col = max(price_cols) + 1 if price_cols else MED_COL

            # Marcador invisible en col Z del col_header_row para detectar duplicados después
            batch_updates.append({"range": rowcol_to_a1(col_header_row, MARKER_COL), "values": [[date_str]]})

            # Fila encabezado de proveedor — igual que fila 1:
            # el primer proveedor arranca desde col A (FECHA_COL) con merge hasta el final,
            # los siguientes solo en sus propias columnas.
            for pc in price_cols:
                if pc == FIRST_PROVIDER_COL:
                    # Primer proveedor: nombre en col A (igual que la fila 1 original)
                    prov_name = prov_row_values[0] if prov_row_values else ""
                    batch_updates.append({"range": rowcol_to_a1(prov_header_row, FECHA_COL), "values": [[prov_name]]})
                else:
                    prov_name = prov_row_values[pc - 1] if pc - 1 < len(prov_row_values) else ""
                    batch_updates.append({"range": rowcol_to_a1(prov_header_row, pc), "values": [[prov_name]]})

            # Fila sub-encabezados
            batch_updates.append({"range": rowcol_to_a1(col_header_row, FECHA_COL), "values": [["Fecha"]]})
            batch_updates.append({"range": rowcol_to_a1(col_header_row, MED_COL), "values": [["Medicamento"]]})
            for pc in price_cols:
                batch_updates.append({"range": rowcol_to_a1(col_header_row, pc), "values": [["Precio"]]})
                batch_updates.append({"range": rowcol_to_a1(col_header_row, pc + 1), "values": [["Cantidad"]]})

            if batch_updates:
                sheet.batch_update(batch_updates)

            # Estilos — mismo patrón que fila 1 y fila 2 originales:
            # fila proveedor: merge desde A hasta última col de unidad, estilo azul
            # fila sub-encabezados: todo desde A hasta última col, estilo azul
            if price_cols:
                # Primer proveedor: merge desde col A
                first_unit_col = FIRST_PROVIDER_COL + 1
                try:
                    sheet.merge_cells(
                        f"{rowcol_to_a1(prov_header_row, FECHA_COL)}:{rowcol_to_a1(prov_header_row, first_unit_col)}"
                    )
                except Exception:
                    pass
                sheet.format(
                    f"{rowcol_to_a1(prov_header_row, FECHA_COL)}:{rowcol_to_a1(prov_header_row, first_unit_col)}",
                    PROVIDER_HEADER_STYLE,
                )
                # Proveedores adicionales: cada uno en sus propias cols
                for pc in price_cols:
                    if pc != FIRST_PROVIDER_COL:
                        try:
                            sheet.merge_cells(
                                f"{rowcol_to_a1(prov_header_row, pc)}:{rowcol_to_a1(prov_header_row, pc + 1)}"
                            )
                        except Exception:
                            pass
                        sheet.format(
                            f"{rowcol_to_a1(prov_header_row, pc)}:{rowcol_to_a1(prov_header_row, pc + 1)}",
                            PROVIDER_HEADER_STYLE,
                        )
                # Sub-encabezados: desde col A hasta última col
                sheet.format(
                    f"{rowcol_to_a1(col_header_row, FECHA_COL)}:{rowcol_to_a1(col_header_row, last_col)}",
                    COL_HEADER_STYLE,
                )

            logger.info(f"Sheets: encabezado de nuevo día insertado en filas {prov_header_row}-{col_header_row}")
            return {"created": True}

        except Exception as e:
            logger.error(f"Error creando encabezado de día en Sheets: {e}")
            raise

    def get_sheet_url(self) -> str:
        if not self._get_sheet_id():
            return ""
        return f"https://docs.google.com/spreadsheets/d/{self._get_sheet_id()}"

    def get_summary(self) -> dict:
        if not self._get_sheet_id():
            return {"configured": False}
        try:
            spreadsheet = self._get_spreadsheet()
            current_sheet = date.today().strftime("%Y-%m")
            all_sheets = [ws.title for ws in spreadsheet.worksheets()]

            if current_sheet not in all_sheets:
                return {"configured": True, "current_sheet": current_sheet, "medications": 0, "providers": [], "url": self.get_sheet_url()}

            sheet = spreadsheet.worksheet(current_sheet)
            provider_row = sheet.row_values(PROVIDER_ROW)
            # Proveedores están desde col C en adelante (ignorar cols A y B)
            providers = [v for v in provider_row[FIRST_PROVIDER_COL - 1:] if v]
            num_rows = len([v for v in sheet.col_values(MED_COL)[DATA_START_ROW - 1:] if v])

            return {
                "configured": True,
                "current_sheet": current_sheet,
                "medications": num_rows,
                "providers": providers,
                "all_sheets": all_sheets,
                "url": self.get_sheet_url(),
            }
        except Exception as e:
            logger.warning(f"No se pudo obtener resumen de Sheets: {e}")
            return {"configured": True, "error": str(e), "url": self.get_sheet_url()}
