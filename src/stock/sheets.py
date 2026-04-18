import json
import os
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CREDS_PATH = PROJECT_ROOT / "src" / "creds.json"
SHEET_ID = os.environ.get("STOCK_SHEET_ID", "1pThrKtAQdOaTgsm-nxj7y-LB685PhPLZd4hx0n0M2C0")


def _get_creds_path() -> Path:
    raw_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.environ.get(
        "STOCK_GOOGLE_CREDS_PATH",
        str(DEFAULT_CREDS_PATH),
    )
    return Path(raw_path).expanduser().resolve()


def get_spreadsheet():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    raw_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw_json:
        creds = Credentials.from_service_account_info(json.loads(raw_json), scopes=scope)
    else:
        creds_path = _get_creds_path()
        if not creds_path.exists():
            raise FileNotFoundError(
                f"Google service account credentials not found at {creds_path}. "
                "Set GOOGLE_APPLICATION_CREDENTIALS, STOCK_GOOGLE_CREDS_PATH, or GOOGLE_SERVICE_ACCOUNT_JSON."
            )

        creds = Credentials.from_service_account_file(
            creds_path,
            scopes=scope,
        )

    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)


def get_sheet(tab_name: str):
    ss = get_spreadsheet()
    return ss.worksheet(tab_name)


def clear_row_groups(sheet) -> None:
    metadata = sheet.spreadsheet.fetch_sheet_metadata()
    target = None

    for sheet_meta in metadata.get("sheets", []):
        props = sheet_meta.get("properties", {})
        if props.get("sheetId") == sheet.id:
            target = sheet_meta
            break

    if target is None:
        return

    requests = []
    for group in reversed(target.get("rowGroups", [])):
        group_range = group.get("range", {})
        requests.append(
            {
                "deleteDimensionGroup": {
                    "range": {
                        "sheetId": sheet.id,
                        "dimension": "ROWS",
                        "startIndex": group_range.get("startIndex", 0),
                        "endIndex": group_range.get("endIndex", 0),
                    }
                }
            }
        )

    if requests:
        sheet.spreadsheet.batch_update({"requests": requests})


def apply_collapsible_row_groups(sheet, row_groups: list[tuple[int, int]]) -> None:
    if not row_groups:
        return

    requests = []
    for start_index, end_index in row_groups:
        requests.append(
            {
                "addDimensionGroup": {
                    "range": {
                        "sheetId": sheet.id,
                        "dimension": "ROWS",
                        "startIndex": start_index,
                        "endIndex": end_index,
                    }
                }
            }
        )
        requests.append(
            {
                "updateDimensionGroup": {
                    "dimensionGroup": {
                        "range": {
                            "sheetId": sheet.id,
                            "dimension": "ROWS",
                            "startIndex": start_index,
                            "endIndex": end_index,
                        },
                        "depth": 1,
                        "collapsed": True,
                    },
                    "fields": "collapsed,depth",
                }
            }
        )

    sheet.spreadsheet.batch_update({"requests": requests})
