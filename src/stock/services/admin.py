from werkzeug.security import generate_password_hash

from ..db import list_users, set_user_active, update_user_password, update_user_role
from .auth import create_user_account, normalize_user_role


def list_user_accounts():
    return list_users()


def create_user_record(username: str, password: str, role: str) -> int:
    return create_user_account(username, password, role)


def update_user_role_record(user_id: int, role: str) -> None:
    update_user_role(user_id, normalize_user_role(role))


def update_user_active_record(user_id: int, is_active: bool) -> None:
    set_user_active(user_id, is_active)


def reset_user_password(user_id: int, password: str) -> None:
    if len(password or "") < 8:
        raise ValueError("Password must be at least 8 characters long.")
    update_user_password(user_id, generate_password_hash(password))
