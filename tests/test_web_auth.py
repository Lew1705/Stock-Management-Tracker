from stock.services.auth import create_user_account


def login(client, username: str, password: str, next_url: str = "/"):
    return client.post(
        "/login",
        data={"username": username, "password": password, "next": next_url},
        follow_redirects=False,
    )


def test_protected_pages_redirect_to_login(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_staff_can_log_in_and_run_day(client, monkeypatch):
    create_user_account("staff1", "password123", "staff")

    login_response = login(client, "staff1", "password123")
    assert login_response.status_code == 302

    monkeypatch.setattr(
        "stock.web.get_daily_sync_readiness",
        lambda run_date: {
            "count_date": run_date,
            "locations": [],
            "is_ready": True,
            "missing_locations": [],
        },
    )
    monkeypatch.setattr("stock.web.run_daily_workflow", lambda run_date: None)
    monkeypatch.setattr("stock.web.save_run_history", lambda *args, **kwargs: 1)

    response = client.post("/run-day", data={"run_date": "2026-04-24"}, follow_redirects=False)

    assert response.status_code == 200
    assert b"Run complete" in response.data


def test_staff_cannot_open_manager_inventory_form(client):
    create_user_account("staff2", "password123", "staff")
    login(client, "staff2", "password123")

    response = client.get("/items/new", follow_redirects=False)

    assert response.status_code == 403


def test_manager_can_open_manager_inventory_form(client):
    create_user_account("manager1", "password123", "manager")
    login(client, "manager1", "password123")

    response = client.get("/items/new", follow_redirects=False)

    assert response.status_code == 200
    assert b"Add item" in response.data


def test_admin_can_open_user_management_page(client):
    create_user_account("admin1", "password123", "admin")
    login(client, "admin1", "password123")

    response = client.get("/admin/users", follow_redirects=False)

    assert response.status_code == 200
    assert b"User management" in response.data
