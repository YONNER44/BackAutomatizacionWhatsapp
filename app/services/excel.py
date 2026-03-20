import logging
from datetime import date
from pathlib import Path
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

GREEN_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
GREEN_FONT = Font(bold=True, color="276221")
NO_FILL = PatternFill(fill_type=None)
NORMAL_FONT = Font()


class ExcelService:
    def __init__(self):
        self.output_path = Path(settings.EXCEL_OUTPUT_PATH)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_or_create_workbook(self):
        if self.output_path.exists():
            return load_workbook(self.output_path)
        wb = Workbook()
        # Eliminar hoja por defecto
        wb.remove(wb.active)
        return wb

    def _apply_header_style(self, cell):
        cell.font = Font(bold=True, color="FFFFFF", size=11)
        cell.fill = PatternFill(start_color="2E75B6", end_color="2E75B6", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    def _apply_border(self, cell):
        thin = Side(style="thin")
        cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def _get_or_create_monthly_sheet(self, wb, sheet_name: str):
        """Obtiene o crea la hoja del mes actual."""
        if sheet_name in wb.sheetnames:
            return wb[sheet_name]
        ws = wb.create_sheet(title=sheet_name)
        # Col A: Fecha, Col B: Medicamento, Col C: Cantidad, Col D+: Proveedores
        ws.cell(1, 1, "Fecha")
        self._apply_header_style(ws.cell(1, 1))
        ws.cell(1, 2, "Medicamento")
        self._apply_header_style(ws.cell(1, 2))
        ws.cell(1, 3, "Cantidad")
        self._apply_header_style(ws.cell(1, 3))
        ws.column_dimensions["A"].width = 12
        ws.column_dimensions["B"].width = 35
        ws.column_dimensions["C"].width = 15
        return ws

    def _mark_best_prices(self, ws, first_provider_col: int):
        """Marca en verde el precio más bajo de cada fila (medicamento)."""
        for row in range(2, ws.max_row + 1):
            if not ws.cell(row, 2).value:  # Col B = Medicamento
                continue

            prices = []
            for col in range(first_provider_col, ws.max_column + 1):
                val = ws.cell(row, col).value
                if isinstance(val, (int, float)):
                    prices.append((col, val))

            if len(prices) < 2:
                continue  # Sin comparación posible con un solo proveedor

            min_price = min(v for _, v in prices)

            for col in range(first_provider_col, ws.max_column + 1):
                cell = ws.cell(row, col)
                if isinstance(cell.value, (int, float)) and cell.value == min_price:
                    cell.fill = GREEN_FILL
                    cell.font = GREEN_FONT
                else:
                    cell.fill = NO_FILL
                    cell.font = NORMAL_FONT

    def update_prices(self, provider_name: str, prices: list[dict], report_date: date = None) -> str:
        """
        Actualiza el archivo Excel con los precios del proveedor.
        - Una hoja por mes: "YYYY-MM" (ej: "2026-03")
        - Medicamentos en filas (columna A)
        - Proveedores en columnas (B en adelante)
        - El precio más bajo de cada fila se marca en verde automáticamente
        """
        if not prices:
            logger.info(f"No hay precios para actualizar de proveedor: {provider_name}")
            return str(self.output_path)

        report_date = report_date or date.today()
        sheet_name = report_date.strftime("%Y-%m")  # ej: "2026-03"

        wb = self._get_or_create_workbook()
        ws = self._get_or_create_monthly_sheet(wb, sheet_name)

        # Encontrar o crear columna del proveedor (empieza en col D=4)
        # Col A=Fecha, Col B=Medicamento, Col C=Cantidad, Col D+=Proveedores
        provider_col = None
        first_provider_col = 4
        for col in range(first_provider_col, ws.max_column + 2):
            cell_val = ws.cell(1, col).value
            if cell_val == provider_name:
                provider_col = col
                break
            if cell_val is None:
                provider_col = col
                ws.cell(1, col, provider_name)
                self._apply_header_style(ws.cell(1, col))
                ws.column_dimensions[get_column_letter(col)].width = 20
                break

        # Índice de medicamentos existentes (col B = Medicamento)
        med_rows = {}
        for row in range(2, ws.max_row + 1):
            val = ws.cell(row, 2).value
            if val and isinstance(val, str):
                med_rows[val.lower()] = row

        def find_med_key(search_key: str) -> str | None:
            from difflib import SequenceMatcher
            if search_key in med_rows:
                return search_key
            search_words = set(search_key.split())
            best_word, best_overlap = None, 0
            for k in med_rows:
                kw = set(k.split())
                if search_words.issubset(kw) or kw.issubset(search_words):
                    overlap = len(search_words & kw)
                    if overlap > best_overlap:
                        best_overlap, best_word = overlap, k
            if best_word:
                return best_word
            best_fuzzy, best_ratio = None, 0.0
            for k in med_rows:
                r = SequenceMatcher(None, search_key, k).ratio()
                if r >= 0.80 and r > best_ratio:
                    best_ratio, best_fuzzy = r, k
            return best_fuzzy

        # Próxima fila disponible
        next_available_row = (max(med_rows.values()) + 1) if med_rows else 2

        # Insertar/actualizar precios
        for item in prices:
            med_name = item.get("medication_name", "").strip()
            price_val = item.get("price")
            unit = item.get("unit") or ""

            if not med_name or price_val is None:
                continue

            key = med_name.lower()
            matched_key = find_med_key(key)

            if matched_key is None:
                # Col A: Fecha, Col B: Medicamento, Col C: Cantidad
                date_cell = ws.cell(next_available_row, 1, report_date.strftime("%d/%m/%Y"))
                self._apply_border(date_cell)
                ws.cell(next_available_row, 2, med_name)
                self._apply_border(ws.cell(next_available_row, 2))
                if unit:
                    ws.cell(next_available_row, 3, unit)
                    self._apply_border(ws.cell(next_available_row, 3))
                med_rows[key] = next_available_row
                next_available_row += 1
            else:
                # Actualizar fecha y cantidad si es necesario
                date_cell = ws.cell(med_rows[matched_key], 1, report_date.strftime("%d/%m/%Y"))
                self._apply_border(date_cell)
                if unit:
                    ws.cell(med_rows[matched_key], 3, unit)

            row_idx = med_rows[matched_key]
            price_cell = ws.cell(row_idx, provider_col, price_val)
            price_cell.number_format = "#,##0.00"
            self._apply_border(price_cell)

        # Marcar mejor precio en verde (proveedores desde col 4)
        self._mark_best_prices(ws, first_provider_col)

        wb.save(self.output_path)
        logger.info(f"Excel actualizado: hoja '{sheet_name}', proveedor '{provider_name}', {len(prices)} precios")
        return str(self.output_path)

    def generate_report(self, prices_data: list[dict]) -> bytes:
        """
        Genera Excel desde datos de la BD con el mismo formato que Google Sheets.
        prices_data: lista de {medication_name, price, unit, provider_name, date_reported}
        Una hoja por mes. Formato: Fecha | Medicamento | Precio+Cantidad por proveedor.
        """
        from io import BytesIO

        wb = Workbook()
        wb.remove(wb.active)

        # Agrupar por mes
        months = sorted(set(p["date_reported"].strftime("%Y-%m") for p in prices_data))

        for month in months:
            month_prices = [p for p in prices_data if p["date_reported"].strftime("%Y-%m") == month]
            ws = wb.create_sheet(title=month)

            # Orden de proveedores según primera aparición
            providers = []
            for p in month_prices:
                if p["provider_name"] not in providers:
                    providers.append(p["provider_name"])

            # Col A=Fecha, Col B=Medicamento, luego 2 cols por proveedor
            ws.cell(2, 1, "Fecha"); self._apply_header_style(ws.cell(2, 1))
            ws.cell(2, 2, "Medicamento"); self._apply_header_style(ws.cell(2, 2))
            ws.column_dimensions["A"].width = 12
            ws.column_dimensions["B"].width = 38

            provider_cols = {}
            for i, prov in enumerate(providers):
                price_col = 3 + i * 2
                unit_col = price_col + 1
                provider_cols[prov] = price_col

                # Fila 2: Precio, Cantidad
                ws.cell(2, price_col, "Precio"); self._apply_header_style(ws.cell(2, price_col))
                ws.cell(2, unit_col, "Cantidad"); self._apply_header_style(ws.cell(2, unit_col))
                ws.column_dimensions[get_column_letter(price_col)].width = 16
                ws.column_dimensions[get_column_letter(unit_col)].width = 14

                # Fila 1: nombre del proveedor combinado
                if price_col == 3:
                    ws.cell(1, 1, prov)
                    self._apply_header_style(ws.cell(1, 1))
                    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=unit_col)
                else:
                    ws.cell(1, price_col, prov)
                    self._apply_header_style(ws.cell(1, price_col))
                    ws.merge_cells(start_row=1, start_column=price_col, end_row=1, end_column=unit_col)

            # Pivot: {med_key: {name, date, provider_name: {price, unit}}}
            # Ordenar por fecha para que el último precio prevalezca en duplicados
            pivot = {}
            med_order = []
            for p in sorted(month_prices, key=lambda x: x["date_reported"]):
                key = p["medication_name"].lower()
                if key not in pivot:
                    pivot[key] = {"name": p["medication_name"], "date": p["date_reported"]}
                    med_order.append(key)
                pivot[key][p["provider_name"]] = {
                    "price": p["price"],
                    "unit": p["unit"] or "NO",
                    "date": p["date_reported"],
                }

            # Escribir filas de datos
            for row_num, key in enumerate(med_order, start=3):
                data = pivot[key]

                # Fecha: la más reciente entre proveedores
                latest_date = max(
                    (data[pn]["date"] for pn in providers if pn in data),
                    default=data["date"],
                )
                date_cell = ws.cell(row_num, 1, latest_date.strftime("%d/%m/%Y"))
                self._apply_border(date_cell)

                med_cell = ws.cell(row_num, 2, data["name"])
                self._apply_border(med_cell)

                provider_prices = []
                for prov_name in providers:
                    price_col = provider_cols[prov_name]
                    unit_col = price_col + 1
                    if prov_name in data:
                        price_cell = ws.cell(row_num, price_col, data[prov_name]["price"])
                        price_cell.number_format = "#,##0.00"
                        self._apply_border(price_cell)
                        provider_prices.append((price_col, data[prov_name]["price"]))
                        unit_cell = ws.cell(row_num, unit_col, data[prov_name]["unit"])
                        self._apply_border(unit_cell)
                    else:
                        ws.cell(row_num, price_col, "NO"); self._apply_border(ws.cell(row_num, price_col))
                        ws.cell(row_num, unit_col, "NO"); self._apply_border(ws.cell(row_num, unit_col))

                # Marcar precio más bajo en verde
                if len(provider_prices) >= 2:
                    min_price = min(v for _, v in provider_prices)
                    for col, val in provider_prices:
                        cell = ws.cell(row_num, col)
                        if val == min_price:
                            cell.fill = GREEN_FILL
                            cell.font = GREEN_FONT
                        else:
                            cell.fill = NO_FILL
                            cell.font = NORMAL_FONT

        output = BytesIO()
        wb.save(output)
        output.seek(0)
        return output.getvalue()

    def get_summary(self) -> dict:
        if not self.output_path.exists():
            return {"exists": False, "medications": 0, "providers": []}

        wb = load_workbook(self.output_path)
        current_sheet = date.today().strftime("%Y-%m")

        if current_sheet not in wb.sheetnames:
            return {"exists": True, "medications": 0, "providers": [], "sheets": wb.sheetnames}

        ws = wb[current_sheet]
        providers = []
        for col in range(2, ws.max_column + 1):
            val = ws.cell(1, col).value
            if val:
                providers.append(val)

        medications = sum(1 for row in range(2, ws.max_row + 1) if ws.cell(row, 2).value)

        return {
            "exists": True,
            "current_sheet": current_sheet,
            "medications": medications,
            "providers": providers,
            "file_path": str(self.output_path),
            "all_sheets": wb.sheetnames,
        }
