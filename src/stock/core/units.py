import re

VALID_BASE_UNITS = (
    "each",
    "g",
    "ml",
    "pack",
    "tray",
    "roll",
    "bundle",
    "pack of 5",
    "pack of 6",
    "pack of 12",
    "pack of 14",
    "pack of 24",
)


def normalize_base_unit(raw_value: str) -> str:
    value = " ".join((raw_value or "").strip().lower().split())
    if not value:
        raise ValueError("base_unit is required")

    if value in VALID_BASE_UNITS:
        return value

    match = re.fullmatch(r"(pack|tray)(?:\s+of)?\s+(\d+)", value)
    if match:
        unit_type = match.group(1)
        normalized = f"{unit_type} of {int(match.group(2))}"
        return normalized

    raise ValueError(
        "base_unit must be one of the standard units "
        + ", ".join(VALID_BASE_UNITS)
        + ", or a measured package like 'pack of 18' or 'tray of 30'"
    )


def split_multi_value(raw_value: str) -> list[str]:
    value = (raw_value or "").strip()
    if not value:
        return []
    return [part.strip() for part in re.split(r"\s*[|;,]\s*", value) if part.strip()]


def parse_supplier_links(raw_suppliers: str, raw_refs: str) -> list[tuple[str, str]]:
    suppliers = split_multi_value(raw_suppliers)
    refs = split_multi_value(raw_refs)

    if not suppliers:
        return []

    if not refs:
        refs = [""] * len(suppliers)
    elif len(refs) == 1 and len(suppliers) > 1:
        refs = refs * len(suppliers)
    elif len(refs) != len(suppliers):
        raise ValueError(
            "reference values must either be blank, a single shared value, or match the supplier count"
        )

    return list(zip(suppliers, refs))
