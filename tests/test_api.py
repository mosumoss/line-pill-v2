"""routers/api.py (REST API エンドポイント) のテスト。

TDD: GREEN実装は db.py + server.py + routers/api.py。
FastAPI TestClient を使用。認証は dependency_overrides でバイパス。
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from migrations.runner import run_all
from repositories.medications import add_user_medication, list_preset_medications
from repositories.servings import get_or_create_serving
from repositories.users import User, get_or_create_user


# ---------- Fixtures ----------

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Migration 001+002 適用済み DB パス。"""
    path = tmp_path / "test_api.db"
    run_all(path)
    return path


@pytest.fixture
def seeded_user(db_path: Path) -> User:
    """テスト用ユーザーを DB に作成して返す。"""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        user = get_or_create_user(conn, "U_API_001")
    finally:
        conn.close()
    return user


@pytest.fixture
def client(db_path: Path, seeded_user: User) -> TestClient:
    """認証モック済み TestClient。"""
    from db import get_db
    from routers.api import get_current_user
    from server import app

    def override_get_db():
        # check_same_thread=False: TestClient は別スレッドで依存関係を解決するため必要
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: seeded_user

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def authed_client(db_path: Path, seeded_user: User) -> TestClient:
    """認証なしで /api/* にアクセスするためのクライアント (override なし)。"""
    from db import get_db
    from server import app

    def override_get_db():
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    app.dependency_overrides.clear()


# ---------- Auth ----------

class TestAuthRequired:
    def test_no_token_returns_4xx(self, authed_client: TestClient) -> None:
        """認証ヘッダーなし → 401 or 403 (FastAPI HTTPBearer のバージョン依存)。"""
        resp = authed_client.get("/api/me")
        assert resp.status_code in (401, 403)

    def test_invalid_token_returns_401(self, authed_client: TestClient) -> None:
        """無効なトークン → 401。"""
        resp = authed_client.get(
            "/api/me", headers={"Authorization": "Bearer invalid.token.here"}
        )
        assert resp.status_code == 401


# ---------- /api/me ----------

class TestMeEndpoint:
    def test_returns_user_info(self, client: TestClient, seeded_user: User) -> None:
        resp = client.get("/api/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["line_user_id"] == seeded_user.line_user_id
        assert data["id"] == seeded_user.id

    def test_response_contains_role(self, client: TestClient) -> None:
        resp = client.get("/api/me")
        assert "role" in resp.json()


# ---------- /api/settings ----------

class TestSettingsEndpoint:
    def test_get_returns_default_settings(self, client: TestClient) -> None:
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["morning_time"] == "07:30"
        assert data["evening_time"] == "22:00"
        assert data["evening_enabled"] is True
        assert data["timezone"] == "Asia/Tokyo"

    def test_patch_morning_time(self, client: TestClient) -> None:
        resp = client.patch("/api/settings", json={"morning_time": "08:00"})
        assert resp.status_code == 200
        assert resp.json()["morning_time"] == "08:00"

    def test_patch_evening_disabled(self, client: TestClient) -> None:
        resp = client.patch("/api/settings", json={"evening_enabled": False})
        assert resp.status_code == 200
        assert resp.json()["evening_enabled"] is False

    def test_patch_invalid_time_returns_422(self, client: TestClient) -> None:
        resp = client.patch("/api/settings", json={"morning_time": "8am"})
        assert resp.status_code == 422

    def test_patch_unknown_field_returns_422(self, client: TestClient) -> None:
        resp = client.patch("/api/settings", json={"unknown_field": "x"})
        assert resp.status_code == 422


# ---------- /api/medications ----------

class TestMedicationsEndpoint:
    def test_list_presets_returns_six(self, client: TestClient) -> None:
        resp = client.get("/api/medications")
        assert resp.status_code == 200
        assert len(resp.json()) == 6

    def test_each_preset_has_required_fields(self, client: TestClient) -> None:
        resp = client.get("/api/medications")
        for med in resp.json():
            assert "id" in med
            assert "name" in med
            assert "kind" in med


# ---------- /api/user-medications ----------

class TestUserMedicationsEndpoint:
    def test_list_empty_initially(self, client: TestClient) -> None:
        resp = client.get("/api/user-medications?slot=morning")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_add_and_list_medication(
        self, client: TestClient, db_path: Path, seeded_user: User
    ) -> None:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        med_id = list_preset_medications(conn)[0].id
        conn.close()

        resp = client.post(
            "/api/user-medications",
            json={"medication_id": med_id, "slot": "morning"},
        )
        assert resp.status_code == 201

        resp = client.get("/api/user-medications?slot=morning")
        assert len(resp.json()) == 1

    def test_add_invalid_slot_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/api/user-medications",
            json={"medication_id": 1, "slot": "midnight"},
        )
        assert resp.status_code == 422

    def test_remove_medication(self, client: TestClient, db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        presets = list_preset_medications(conn)
        med_id = presets[0].id
        conn.close()

        client.post(
            "/api/user-medications", json={"medication_id": med_id, "slot": "morning"}
        )
        resp = client.delete(f"/api/user-medications/{med_id}?slot=morning")
        assert resp.status_code == 204

        resp = client.get("/api/user-medications?slot=morning")
        assert resp.json() == []

    def test_slot_param_required(self, client: TestClient) -> None:
        resp = client.get("/api/user-medications")
        assert resp.status_code == 422


# ---------- /api/today ----------

class TestTodayEndpoint:
    def test_returns_morning_and_evening(self, client: TestClient) -> None:
        resp = client.get("/api/today")
        assert resp.status_code == 200
        data = resp.json()
        assert "morning" in data
        assert "evening" in data

    def test_servings_have_required_fields(self, client: TestClient) -> None:
        resp = client.get("/api/today")
        data = resp.json()
        for slot_data in data.values():
            assert "id" in slot_data
            assert "scheduled_date" in slot_data
            assert "slot" in slot_data
            assert "taken_at" in slot_data

    def test_idempotent_second_call_same_ids(self, client: TestClient) -> None:
        r1 = client.get("/api/today")
        r2 = client.get("/api/today")
        assert r1.json()["morning"]["id"] == r2.json()["morning"]["id"]


# ---------- /api/servings/{id}/take ----------

class TestMarkTakenEndpoint:
    def test_mark_taken_returns_200(
        self, client: TestClient, db_path: Path, seeded_user: User
    ) -> None:
        today = date.today().isoformat()
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        s = get_or_create_serving(
            conn, user_id=seeded_user.id, date=today, slot="morning"
        )
        conn.close()

        resp = client.post(f"/api/servings/{s.id}/take")
        assert resp.status_code == 200
        assert resp.json()["taken_at"] is not None

    def test_mark_taken_twice_returns_409(
        self, client: TestClient, db_path: Path, seeded_user: User
    ) -> None:
        today = date.today().isoformat()
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        s = get_or_create_serving(
            conn, user_id=seeded_user.id, date=today, slot="evening"
        )
        conn.close()

        client.post(f"/api/servings/{s.id}/take")
        resp = client.post(f"/api/servings/{s.id}/take")
        assert resp.status_code == 409

    def test_mark_taken_nonexistent_returns_404(
        self, client: TestClient
    ) -> None:
        resp = client.post("/api/servings/99999/take")
        assert resp.status_code == 404


# ---------- /api/servings ----------

class TestListServingsEndpoint:
    def test_list_in_date_range(
        self, client: TestClient, db_path: Path, seeded_user: User
    ) -> None:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        get_or_create_serving(
            conn, user_id=seeded_user.id, date="2026-05-01", slot="morning"
        )
        get_or_create_serving(
            conn, user_id=seeded_user.id, date="2026-05-03", slot="morning"
        )
        conn.close()

        resp = client.get("/api/servings?from_date=2026-05-01&to_date=2026-05-05")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_from_and_to_date_required(self, client: TestClient) -> None:
        resp = client.get("/api/servings")
        assert resp.status_code == 422
