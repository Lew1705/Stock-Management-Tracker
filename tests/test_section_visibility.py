from stock.db import list_sections, update_section_visibility
from stock.services.auth import create_user_account
from stock.services.items import save_item_record


def login(client, username: str, password: str, next_url: str = "/"):
    return client.post(
        "/login",
        data={"username": username, "password": password, "next": next_url},
        follow_redirects=False,
    )


def _section_id(name: str) -> int:
    rows = list_sections()
    for row in rows:
        if row["name"] == name:
            return int(row["id"])
    raise AssertionError(f"Section {name} was not found")


def test_staff_api_only_returns_visible_sections(client):
    save_item_record(None, "Sourdough", "Bread", "each", "Booker", "", "1", "5", "0")
    save_item_record(None, "Bleach", "Cleaning Products", "each", "Booker", "", "1", "5", "0")
    update_section_visibility(_section_id("Cleaning Products"), False)
    create_user_account("staff-sections", "password123", "staff")
    login(client, "staff-sections", "password123")

    response = client.get("/api/items")
    names = {row["name"] for row in response.get_json()["items"]}

    assert response.status_code == 200
    assert names == {"Sourdough"}


def test_staff_cannot_update_hidden_section_by_posting_item_id(client):
    bread_id = save_item_record(None, "Sourdough", "Bread", "each", "Booker", "", "1", "5", "0")
    cleaning_id = save_item_record(None, "Bleach", "Cleaning Products", "each", "Booker", "", "1", "5", "0")
    update_section_visibility(_section_id("Cleaning Products"), False)
    create_user_account("staff-hidden-post", "password123", "staff")
    login(client, "staff-hidden-post", "password123")

    response = client.post(
        "/api/counts",
        json={
            "location": "Keele",
            "count_date": "2026-05-15",
            "counts": {str(bread_id): "3", str(cleaning_id): "2"},
        },
    )

    assert response.status_code == 400
    assert "cannot update that section" in response.get_json()["message"]


def test_admin_can_toggle_section_visibility(client):
    save_item_record(None, "Sourdough", "Bread", "each", "Booker", "", "1", "5", "0")
    create_user_account("admin-sections", "password123", "admin")
    login(client, "admin-sections", "password123")

    page = client.get("/admin/sections")
    assert page.status_code == 200
    assert b"Section visibility" in page.data

    response = client.post(
        f"/admin/sections/{_section_id('Bread')}/visibility",
        data={"visible_to_staff": "0"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    bread = next(row for row in list_sections() if row["name"] == "Bread")
    assert not bool(bread["visible_to_staff"])
