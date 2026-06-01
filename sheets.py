import json
import os
import logging

import gspread

logger = logging.getLogger(__name__)

HEADERS = [
    "ID",
    "Дата и время",
    "Приоритет",
    "Категория",
    "Кто сообщил",
    "Источник (чат)",
    "Описание",
    "Комментарий ответственного",
    "Срок",
    "Статус",
    "Необходимые закупки",
    "Стоимость материалов (руб.)",
    "Стоимость доп. работ (руб.)",
]

STATUSES = [
    "🆕 Новая",
    "🔧 В работе",
    "⏳ Ожидает материалов",
    "✅ Выполнена",
    "❌ Отклонена",
]

STATUS_NEW = STATUSES[0]
NUM_COLS = len(HEADERS)  # 13 → A..M


def _get_client() -> gspread.Client:
    creds_raw = os.environ["GOOGLE_CREDS_JSON"]
    creds_info = json.loads(creds_raw)
    return gspread.service_account_from_dict(creds_info)


def _get_spreadsheet() -> gspread.Spreadsheet:
    client = _get_client()
    spreadsheet_id = os.environ.get("SPREADSHEET_ID", "").strip()

    if spreadsheet_id:
        try:
            sp = client.open_by_key(spreadsheet_id)
            logger.info(f"Открыта таблица: {spreadsheet_id}")
            return sp
        except Exception as e:
            logger.error(f"Не могу открыть таблицу {spreadsheet_id!r}: {e}")

    sp = client.create("ClimbLab Инциденты")
    sp.share(None, perm_type="anyone", role="writer")
    logger.warning("=" * 60)
    logger.warning("СОЗДАНА НОВАЯ ТАБЛИЦА!")
    logger.warning(f"ID: {sp.id}")
    logger.warning(f"URL: https://docs.google.com/spreadsheets/d/{sp.id}")
    logger.warning("Сохраните этот ID в переменную SPREADSHEET_ID на Railway!")
    logger.warning("=" * 60)
    return sp


def _get_worksheet(gym: str) -> gspread.Worksheet:
    spreadsheet = _get_spreadsheet()
    tab_name = "Бутырская" if "Бутырская" in gym else "Аминьевская"

    try:
        ws = spreadsheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=tab_name, rows=2000, cols=NUM_COLS)
        ws.append_row(HEADERS, value_input_option="RAW")
        _setup_sheet(spreadsheet, ws)
        logger.info(f"Создан новый лист: {tab_name}")

    return ws


def _setup_sheet(spreadsheet: gspread.Spreadsheet, ws: gspread.Worksheet):
    """Форматирование заголовка, выпадающий список статусов, перенос по словам."""
    last_col = chr(ord("A") + NUM_COLS - 1)  # "M"
    status_col_idx = HEADERS.index("Статус")  # 9 (0-based)

    requests = [
        # ── Заголовок: фон + белый жирный текст ──────────────────────
        {
            "repeatCell": {
                "range": {
                    "sheetId": ws.id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": NUM_COLS,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.12, "green": 0.22, "blue": 0.39},
                        "textFormat": {
                            "bold": True,
                            "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                        },
                        "wrapStrategy": "WRAP",
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,wrapStrategy)",
            }
        },
        # ── Перенос по словам для всех данных ────────────────────────
        {
            "repeatCell": {
                "range": {
                    "sheetId": ws.id,
                    "startRowIndex": 1,
                    "endRowIndex": 2000,
    
