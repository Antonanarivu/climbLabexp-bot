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
    "Новая",
    "В работе",
    "Ожидает материалов",
    "Выполнена",
    "Отклонена",
]

STATUS_NEW = STATUSES[0]
NUM_COLS = len(HEADERS)


def _get_client():
    creds_raw = os.environ["GOOGLE_CREDS_JSON"]
    creds_info = json.loads(creds_raw)
    return gspread.service_account_from_dict(creds_info)


def _get_spreadsheet():
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


def _get_worksheet(gym):
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


def _setup_sheet(spreadsheet, ws):
    status_col_idx = HEADERS.index("Статус")
    requests = [
        {
            "repeatCell": {
                "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": NUM_COLS},
                "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.12, "green": 0.22, "blue": 0.39}, "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}, "wrapStrategy": "WRAP"}},
                "fields": "userEnteredFormat(backgroundColor,textFormat,wrapStrategy)",
            }
        },
        {
            "repeatCell": {
                "range": {"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": 2000, "startColumnIndex": 0, "endColumnIndex": NUM_COLS},
                "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP"}},
                "fields": "userEnteredFormat.wrapStrategy",
            }
        },
        {
            "setDataValidation": {
                "range": {"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": 2000, "startColumnIndex": status_col_idx, "endColumnIndex": status_col_idx + 1},
                "rule": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": s} for s in STATUSES]}, "showCustomUi": True, "strict": False},
            }
        },
        {
            "updateSheetProperties": {
                "properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
    ]
    try:
        spreadsheet.batch_update({"requests": requests})
    except Exception as e:
        logger.warning(f"Не удалось применить форматирование: {e}")


def get_next_id(gym):
    try:
        ws = _get_worksheet(gym)
        all_rows = ws.get_all_values()
        return max(len(all_rows), 1)
    except Exception as e:
        logger.error(f"Ошибка получения ID: {e}")
        return 0


def append_incident(gym, data):
    ws = _get_worksheet(gym)
    description_full = data["description"]
    if data.get("location"):
        description_full += "\n" + data["location"]
    row = [
        data["id"],
        data["datetime"],
        "",
        data["category"],
        data["reporter
