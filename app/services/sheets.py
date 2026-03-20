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

    def _get_spreadsheet(self):
        if self._spreadsheet is not None:
            return self._spreadsheet

        if not settings.GOOGLE_APPLICATION_CREDENTIALS or not settings.GOOGLE_SHEET_ID:
            raise ValueError("Faltan GOOGLE_APPLICATION_CREDENTIALS o GOOGLE_SHEET_ID en .env")

        creds = Credentials.from_service_account_file(
            settings.GOOGLE_APPLICATION_CREDENTIALS,
            scopes=SCOPES,
        )
        self._client = gspread.authorize(creds)
        self._spreadsheet = self._client.open_by_key(settings.GOOGLE_SHEET_ID)
        return self._spreadsheet

    def _get_or_create_monthly_sheet(self, spreadsheet, sheet_name: str):
        """Obtiene o crea la hoja mensual (ej: '2026-03')."""
        try:
            return spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(title=sheet_name, rows=500, cols=50)
            # Fila 2: encabezados compartidos Fecha y Medicamento
            ws.update(f"A{COL_HEADER_ROW}:B{COL_HEADER_ROW}", [["Fecha", "Medicamento"]])
            ws.format(f"A{COL_HEADER_ROW}", COL_HEADER_STYLE)
            ws.format(f"B{COL_HEADER_ROW}", COL_HEADER_STYLE)
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

    def _get_med_row_map(self, sheet) -> dict:
        """Lee medicamentos (col B desde DATA_START_ROW) y retorna {nombre_lower: row_idx}."""
        col_b = sheet.col_values(MED_COL)
        med_map = {}
        for idx, val in enumerate(col_b[DATA_START_ROW - 1:], start=DATA_START_ROW):
            if val:
                med_map[val.lower()] = idx
        return med_map

    def _find_med_key(self, med_row_map: dict, search_key: str) -> str | None:
        """
        Busca medicamento con coincidencia flexible (3 niveles):
        1. Exacto (case-insensitive)
        2. Palabras: "dipirona" coincide con "dipirona 500mg"
        3. Similitud por typos: "aspiria" coincide con "aspirina" (umbral 80%)
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

        # 3. Similitud por caracteres (maneja typos como "aspiria" → "aspirina")
        THRESHOLD = 0.80
        best_match = None
        best_ratio = 0.0
        for existing_key in med_row_map:
            ratio = SequenceMatcher(None, search_key, existing_key).ratio()
            if ratio >= THRESHOLD and ratio > best_ratio:
                best_ratio = ratio
                best_match = existing_key

        if best_match:
            logger.info(f"Coincidencia fuzzy: '{search_key}' → '{best_match}' ({best_ratio:.0%})")
        return best_match

    def _mark_best_prices(self, sheet, price_cols: list[int], med_row_map: dict):
        """Marca en verde el precio más bajo de cada medicamento entre todos los proveedores."""
        from gspread.utils import rowcol_to_a1

        if not price_cols or not med_row_map:
            return

        all_data = sheet.get_all_values()

        for med_name, row_idx in med_row_map.items():
            if row_idx - 1 >= len(all_data):
                continue

            row = all_data[row_idx - 1]
            prices = []
            for col in price_cols:
                if col - 1 < len(row):
                    try:
                        val_str = str(row[col - 1]).strip()
                        if not val_str:
                            continue
                        # Limpiar formato: quitar comas (miles) y puntos finales
                        val_str = val_str.replace(',', '').rstrip('.')
                        val = float(val_str)
                        if val > 0:
                            prices.append((col, val))
                    except (ValueError, TypeError):
                        pass

            if len(prices) < 2:
                # Sin comparación posible: limpiar cualquier verde previo
                for col, _ in prices:
                    try:
                        sheet.format(rowcol_to_a1(row_idx, col), NO_STYLE)
                    except Exception:
                        pass
                continue

            min_price = min(v for _, v in prices)

            for col, val in prices:
                cell = rowcol_to_a1(row_idx, col)
                style = GREEN_STYLE if val == min_price else NO_STYLE
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

            med_row_map = self._get_med_row_map(sheet)

            # Si el proveedor es nuevo, llenar filas existentes con "NO" en Precio y Cantidad
            if is_new_provider and med_row_map:
                no_updates = []
                for _, row_idx in med_row_map.items():
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

            next_available_row = (max(med_row_map.values()) + 1) if med_row_map else DATA_START_ROW

            # Leer datos actuales para no sobreescribir precios existentes
            all_current_data = sheet.get_all_values()

            batch_updates = []
            updated_keys = set()

            for item in prices:
                med_name = item.get("medication_name", "").strip()
                price_val = item.get("price")
                unit_val = item.get("unit") or ""

                if not med_name or price_val is None:
                    continue

                key = med_name.lower()
                matched_key = self._find_med_key(med_row_map, key)
                updated_keys.add(matched_key if matched_key else key)

                if matched_key is None:
                    # Fila nueva: escribir Fecha en col A, Medicamento en col B
                    batch_updates.append({
                        "range": rowcol_to_a1(next_available_row, FECHA_COL),
                        "values": [[date_str]],
                    })
                    batch_updates.append({
                        "range": rowcol_to_a1(next_available_row, MED_COL),
                        "values": [[med_name]],
                    })
                    batch_updates.append({
                        "range": rowcol_to_a1(next_available_row, provider_price_col),
                        "values": [[price_val]],
                    })
                    # Siempre escribir Cantidad (unidad o "NO" si no hay)
                    batch_updates.append({
                        "range": rowcol_to_a1(next_available_row, provider_unit_col),
                        "values": [[unit_val if unit_val else "NO"]],
                    })
                    # Llenar otros proveedores existentes con "NO"
                    for other_col in existing_price_cols:
                        if other_col != provider_price_col:
                            batch_updates.append({
                                "range": rowcol_to_a1(next_available_row, other_col),
                                "values": [["NO"]],
                            })
                            batch_updates.append({
                                "range": rowcol_to_a1(next_available_row, other_col + 1),
                                "values": [["NO"]],
                            })
                    med_row_map[key] = next_available_row
                    next_available_row += 1
                else:
                    row_idx = med_row_map[matched_key]
                    # Actualizar fecha y precio
                    batch_updates.append({
                        "range": rowcol_to_a1(row_idx, FECHA_COL),
                        "values": [[date_str]],
                    })
                    batch_updates.append({
                        "range": rowcol_to_a1(row_idx, provider_price_col),
                        "values": [[price_val]],
                    })
                    # Actualizar Cantidad (unidad o "NO" si no hay)
                    batch_updates.append({
                        "range": rowcol_to_a1(row_idx, provider_unit_col),
                        "values": [[unit_val if unit_val else "NO"]],
                    })

            # Medicamentos existentes que este proveedor NO ofrece en este mensaje:
            # poner "NO" en Precio y Cantidad SOLO si la celda está vacía
            for existing_key, row_idx in med_row_map.items():
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

            # Marcar mejor precio en verde — detectar columnas "Precio" en fila 2
            header_row = sheet.row_values(COL_HEADER_ROW)
            all_price_cols = [i + 1 for i, v in enumerate(header_row) if v == "Precio"]
            self._mark_best_prices(sheet, all_price_cols, self._get_med_row_map(sheet))

            logger.info(f"Sheets actualizado: hoja '{sheet_name}', '{provider_name}', {len(prices)} precios")
            return self.get_sheet_url()

        except Exception as e:
            logger.error(f"Error actualizando Google Sheets: {e}")
            raise

    def get_sheet_url(self) -> str:
        if not settings.GOOGLE_SHEET_ID:
            return ""
        return f"https://docs.google.com/spreadsheets/d/{settings.GOOGLE_SHEET_ID}"

    def get_summary(self) -> dict:
        if not settings.GOOGLE_SHEET_ID:
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
