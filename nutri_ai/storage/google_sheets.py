"""Google Sheets provider: one row per food item in a worksheet called "meals".

Values are written RAW, so numbers are real numbers and the date/time columns
are plain ISO text ("2026-11-14", "12:30"). Text dates still sort, filter and
pivot correctly in Sheets, and they read back identically in every locale.
"""

from datetime import datetime
from typing import Optional

import gspread

from ..models import MealEntry
from .base import COLUMNS, MealStore, entry_to_row, matches, row_to_entry

WORKSHEET = "meals"


class GoogleSheetsStore(MealStore):
    def __init__(self, sheet_id: str, credentials_file: str):
        if not sheet_id:
            raise ValueError("GOOGLE_SHEET_ID is not set")
        client = gspread.service_account(filename=credentials_file)
        spreadsheet = client.open_by_key(sheet_id)
        try:
            self.sheet = spreadsheet.worksheet(WORKSHEET)
        except gspread.WorksheetNotFound:
            self.sheet = spreadsheet.add_worksheet(WORKSHEET, rows=1000, cols=len(COLUMNS))
        if self.sheet.row_values(1) != COLUMNS:
            if self.sheet.row_values(1):
                raise ValueError(
                    f'Worksheet "{WORKSHEET}" has an unexpected header row. '
                    "Use an empty worksheet or restore the original headers."
                )
            self.sheet.append_row(COLUMNS, value_input_option="RAW")
            self.sheet.freeze(rows=1)

    def add_entries(self, entries: list[MealEntry]) -> None:
        self.sheet.append_rows([entry_to_row(e) for e in entries], value_input_option="RAW")

    def get_entries(
        self, start: datetime, end: datetime, person: Optional[str] = None
    ) -> list[MealEntry]:
        entries = [row_to_entry(r) for r in self.sheet.get_all_records() if r.get("meal_id")]
        return [e for e in entries if matches(e, start, end, person)]

    def delete_meal(self, meal_id: str) -> int:
        ids = self.sheet.col_values(1)  # includes the header, so index 0 is row 1
        rows = [i + 1 for i, value in enumerate(ids) if value == meal_id]
        for row in reversed(rows):  # bottom-up so row numbers stay valid
            self.sheet.delete_rows(row)
        return len(rows)
