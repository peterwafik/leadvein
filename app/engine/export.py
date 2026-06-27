from __future__ import annotations

import csv
import io

from openpyxl import Workbook, load_workbook


def _stringify(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value)
    if isinstance(value, dict):
        return "; ".join(f"{k}={v}" for k, v in value.items())
    if isinstance(value, bool):
        return "Y" if value else "N"
    return str(value)


def rows_to_csv(columns: list[str], rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_stringify(row.get(c, "")) for c in columns])
    return buf.getvalue().encode("utf-8")


def rows_to_xlsx(sheet_name: str, columns: list[str], rows: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]  # Excel tab name limit
    ws.append(columns)
    for row in rows:
        ws.append([_stringify(row.get(c, "")) for c in columns])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def append_xlsx(existing: bytes, sheet_name: str, rows: list[dict]) -> bytes:
    wb = load_workbook(io.BytesIO(existing))
    name = sheet_name[:31]
    if name in wb.sheetnames:
        ws = wb[name]
    else:
        ws = wb.create_sheet(name)
    header = [c.value for c in ws[1] if c.value is not None]
    if not header:
        header = list(rows[0].keys()) if rows else []
        ws.append(header)
    for row in rows:
        ws.append([_stringify(row.get(col, "")) for col in header])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
