import os
import uuid
from pathlib import Path

from werkzeug.datastructures import FileStorage

from .orders import get_order_detail, list_orders
from ..db import (
    create_supplier_invoice,
    get_supplier_invoice,
    list_supplier_invoices,
    mark_supplier_invoice_reviewed,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
INVOICE_UPLOAD_ROOT = Path(
    os.environ.get("STOCK_INVOICE_UPLOAD_PATH", str(PROJECT_ROOT / "uploads" / "invoices"))
).expanduser().resolve()
ALLOWED_INVOICE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}


def _safe_invoice_filename(original_filename: str) -> str:
    extension = Path(original_filename or "").suffix.lower()
    if extension not in ALLOWED_INVOICE_EXTENSIONS:
        raise ValueError("Invoice file must be a PDF, PNG, JPG, JPEG, or WEBP file.")
    return f"{uuid.uuid4().hex}{extension}"


def get_invoice_upload_root() -> Path:
    INVOICE_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    return INVOICE_UPLOAD_ROOT


def build_invoice_hub_data() -> dict:
    ordered_orders = list_orders(status="ORDERED")
    draft_orders = list_orders(status="DRAFT")
    recent_invoices = [dict(row) for row in list_supplier_invoices(limit=20)]
    return {
        "ordered_orders": ordered_orders,
        "draft_orders": draft_orders,
        "recent_invoices": recent_invoices,
        "ordered_count": len(ordered_orders),
        "draft_count": len(draft_orders),
        "invoice_count": len(recent_invoices),
    }


def save_supplier_invoice_upload(
    order_id: str,
    invoice_reference: str,
    supplier_name: str,
    note: str,
    upload: FileStorage | None,
) -> int:
    if upload is None or not (upload.filename or "").strip():
        raise ValueError("Choose the invoice photo or PDF to upload.")

    try:
        normalized_order_id = int((order_id or "").strip())
    except ValueError as exc:
        raise ValueError("Choose the supplier order that matches this invoice.") from exc

    original_filename = upload.filename.strip()
    stored_filename = _safe_invoice_filename(original_filename)
    destination = get_invoice_upload_root() / stored_filename
    upload.save(destination)

    try:
        return create_supplier_invoice(
            normalized_order_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            content_type=(upload.mimetype or "").strip(),
            invoice_reference=invoice_reference,
            supplier_name=supplier_name,
            note=note,
        )
    except Exception:
        if destination.exists():
            destination.unlink(missing_ok=True)
        raise


def get_invoice_detail(invoice_id: int) -> dict:
    invoice = dict(get_supplier_invoice(invoice_id))
    order = get_order_detail(int(invoice["order_id"]))
    return {
        "invoice": invoice,
        "order": order,
    }


def review_invoice(invoice_id: int, invoice_reference: str = "", note: str = "") -> None:
    mark_supplier_invoice_reviewed(invoice_id, invoice_reference=invoice_reference, note=note)


def get_invoice_file_path(stored_filename: str) -> Path:
    path = get_invoice_upload_root() / stored_filename
    if not path.exists():
        raise ValueError("Uploaded invoice file was not found on disk.")
    return path
