import json
import os
import logging

import gspread

logger = logging.getLogger(__name__)

HEADERS = [
    "ID",
    "Дата/время",
    "Кто сообщил",
    "Скалодром",
    "Категория",
    "Описание",
    "Место/уточнение",
    "Медиафайлы",
    "Комментарий ответственного",
    "Плановая дата решения",
    "Необходимые закупки",
    "Стоимость материалов (руб.)",
    "Стоимость доп. работ (руб.)",
    "Статус",
    "Фактическая дата устранения",
]

STATUS_NEW = "🆕 Новая"


def _get_client() -> gspread.Client:
    creds_raw = os.environ["GOOGLE_CREDS_JSON"]
    creds_info = json.loads(creds_raw)
    logger.info(f"Используется сервисный аккаунт: {creds_info.get('client_email', 'НЕТ EMAIL')}")
    return gspread.service_account_from_dict(creds_info)


def _get_worksheet(gym: str) -> gspread.Worksheet:
    client = _get_client()
    spreadsheet_id = os.environ["SPREADSHEET_ID"]
    logger.info(f"Открываю таблицу ID={repr(spreadsheet_id)} (длина={len(spreadsheet_id)})")
    spreadsheet = client.open_by_key(spreadsheet_id)

    tab_name = "Бутырская" if "Бутырская" in gym else "Аминьевская"

    try:
        ws = spreadsheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=tab_name, rows=2000, cols=len(HEADERS))
        ws.append_row(HEADERS, value_input_option="RAW")
        _format_header(ws)
        logger.info(f"Создан новый лист: {tab_name}")

    return ws


def _format_header(ws: gspread.Worksheet):
    try:
        ws.format("A1:O1", {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.12, "green": 0.22, "blue": 0.39},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        })
        ws.freeze(rows=1)
    except Exception as e:
        logger.warning(f"Не удалось отформатировать заголовок: {e}")


def get_next_id(gym: str) -> int:
    try:
        ws = _get_worksheet(gym)
        all_rows = ws.get_all_values()
        return max(len(all_rows), 1)
    except Exception as e:
        logger.error(f"Тип ошибки: {type(e).__name__}")
        logger.error(f"Ошибка получения ID: {e}")
        try:
            logger.error(f"Тело ответа: {e.response.text}")
        except Exception as e2:
            logger.error(f"response.text недоступен: {e2}")
        return 0


def append_incident(gym: str, data: dict):
    ws = _get_worksheet(gym)
    row = [
        data["id"],
        data["datetime"],
        data["reporter"],
        data["gym"],
        data["category"],
        data["description"],
        data["location"],
        data["media"],
        "",
        "",
        "",
        "",
        "",
        STATUS_NEW,
        "",
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    logger.info(f"Добавлена заявка #{data['id']} в лист «{gym}»")
