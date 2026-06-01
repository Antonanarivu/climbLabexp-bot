import json
import os
import logging

import gspread

logger = logging.getLogger(__name__)

# 13 колонок: бот заполняет все кроме Приоритета, Комментария, Срока, Закупок, Стоимостей
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
    "\U0001f195 Новая",
    "\U0001f527 В работе",
    "⏳ Ожидает материалов",
    "✅ Выполнена",
    "❌ Отклонена",
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
            logger.info("Открыта таблица: %s", spreadsheet_id)
            return sp
        except Exception as e:
            logger.error("Не могу открыть таблицу %r: %s", spreadsheet_id, e)
    sp = client.create("ClimbLab Инциденты")
    sp.share(None, perm_type="anyone", role="writer")
    logger.warning("СОЗДАНА НОВАЯ ТАБЛИЦА! ID: %s", sp.id)
    logger.warning("URL: https://docs.google.com/spreadsheets/d/%s", sp.id)
    logger.warning("Сохраните этот ID в переменную SPREADSHEET_ID на Railway!")
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
        logger.info("Создан новый лист: %s", tab_name)
    return ws


def _setup_sheet(spreadsheet, ws):
    status_col_idx = HEADERS.index("Статус")
    requests = [
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
        {
            "repeatCell": {
                "range": {
                    "sheetId": ws.id,
                    "startRowIndex": 1,
                    "endRowIndex": 2000,
                    "startColumnIndex": 0,
                    "endColumnIndex": NUM_COLS,
                },
                "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP"}},
                "fields": "userEnteredFormat.wrapStrategy",
            }
        },
        {
            "setDataValidation": {
                "range": {
                    "sheetId": ws.id,
                    "startRowIndex": 1,
                    "endRowIndex": 2000,
                    "startColumnIndex": status_col_idx,
                    "endColumnIndex": status_col_idx + 1,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": s} for s in STATUSES],
                    },
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        },
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": ws.id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        },
    ]
    try:
        spreadsheet.batch_update({"requests": requests})
    except Exception as e:
        logger.warning("Не удалось применить форматирование: %s", e)


def get_next_id(gym):
    try:
        ws = _get_worksheet(gym)
        all_rows = ws.get_all_values()
        return max(len(all_rows), 1)
    except Exception as e:
        logger.error("Ошибка получения ID: %s", e)
        return 0


def append_incident(gym, data):
    ws = _get_worksheet(gym)
    description_full = data["description"]
    if data.get("location"):
        description_full += "\n\U0001f4cc " + data["location"]
    row = [
        data["id"],
        data["datetime"],
        "",
        data["category"],
        data["reporter"],
        data.get("source_chat", "-"),
        description_full,
        "",
        "",
        STATUS_NEW,
        "",
        "",
        "",
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    logger.info("Добавлена заявка #%s в лист '%s'", data["id"], gym)
