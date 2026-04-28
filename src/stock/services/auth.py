from collections.abc import Iterable
from dataclasses import dataclass
from functools import wraps

from flask import abort, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import create_user, get_user_by_id, get_user_by_username

VALID_USER_ROLES = ("staff", "manager", "admin")


@dataclass
class AnonymousUser:
    id: str | None = None
    username: str = ""
    role: str = ""
    is_active: bool = False
    is_authenticated: bool = False

    def has_any_role(self, roles: Iterable[str]) -> bool:
        return False


@dataclass
class AuthenticatedUser:
    id: str
    username: str
    role: str
    is_active: bool = True
    is_authenticated: bool = True

    def has_any_role(self, roles: Iterable[str]) -> bool:
        allowed = {normalize_user_role(role) for role in roles}
        return self.role in allowed


def normalize_username(username: str) -> str:
    cleaned = " ".join((username or "").strip().split())
    if not cleaned:
        raise ValueError("Username is required.")
    return cleaned.lower()


def normalize_user_role(role: str) -> str:
    cleaned = (role or "").strip().lower()
    if cleaned not in VALID_USER_ROLES:
        allowed = ", ".join(VALID_USER_ROLES)
        raise ValueError(f"Role must be one of: {allowed}.")
    return cleaned


def create_user_account(username: str, password: str, role: str = "staff") -> int:
    normalized_username = normalize_username(username)
    normalized_role = normalize_user_role(role)

    if len(password or "") < 8:
        raise ValueError("Password must be at least 8 characters long.")

    password_hash = generate_password_hash(password)
    return create_user(normalized_username, password_hash, normalized_role)


def authenticate_user(username: str, password: str) -> AuthenticatedUser | None:
    normalized_username = normalize_username(username)
    row = get_user_by_username(normalized_username)
    if row is None or not row["is_active"]:
        return None
    if not check_password_hash(str(row["password_hash"]), password or ""):
        return None
    return user_from_row(row)


def load_authenticated_user(user_id: str | int | None) -> AuthenticatedUser | None:
    if user_id in (None, ""):
        return None
    row = get_user_by_id(int(user_id))
    if row is None or not row["is_active"]:
        return None
    return user_from_row(row)


def user_from_row(row) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=str(int(row["id"])),
        username=str(row["username"]),
        role=str(row["role"]),
        is_active=bool(row["is_active"]),
    )


def get_current_user() -> AuthenticatedUser | AnonymousUser:
    return getattr(g, "current_user", AnonymousUser())


def login_user(user: AuthenticatedUser) -> None:
    session["user_id"] = int(user.id)


def logout_user() -> None:
    session.pop("user_id", None)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if not user.is_authenticated:
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for("login", next=next_url))
        return view(*args, **kwargs)

    return wrapped


def role_required(*roles: str):
    normalized_roles = tuple(normalize_user_role(role) for role in roles)

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = get_current_user()
            if not user.is_authenticated:
                next_url = request.full_path if request.query_string else request.path
                return redirect(url_for("login", next=next_url))
            if not user.has_any_role(normalized_roles):
                return abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
