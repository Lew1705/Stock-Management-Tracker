from ..db import get_staff_visible_sections, list_sections, update_section_visibility
from .auth import AnonymousUser, AuthenticatedUser


def user_can_view_all_sections(user: AuthenticatedUser | AnonymousUser) -> bool:
    return bool(user.is_authenticated and user.role in {"manager", "admin"})


def visible_categories_for_user(user: AuthenticatedUser | AnonymousUser) -> list[str] | None:
    if user_can_view_all_sections(user):
        return None
    if not user.is_authenticated:
        return []
    return get_staff_visible_sections()


def list_section_settings() -> list[dict]:
    return [
        {
            "id": int(row["id"]),
            "name": str(row["name"]),
            "visible_to_staff": bool(row["visible_to_staff"]),
            "created_at": str(row["created_at"]),
        }
        for row in list_sections()
    ]


def save_section_visibility(section_id: int, visible_to_staff: bool) -> None:
    update_section_visibility(section_id, visible_to_staff)
