"""repositories/users.py のテスト。

TDD: GREEN実装は repositories/users.py。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from migrations.runner import run_001
from repositories.users import (
    User,
    UserSettings,
    get_or_create_user,
    get_settings,
    get_user_by_id,
    update_settings,
)


@pytest.fixture
def db(empty_db: Path) -> sqlite3.Connection:
    """Migration 001 適用済み DB への接続。テスト後は自動 close。"""
    run_001(empty_db)
    conn = sqlite3.connect(empty_db)
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


class TestGetOrCreateUser:
    def test_creates_new_user(self, db: sqlite3.Connection) -> None:
        user = get_or_create_user(db, "U_NEW_001")
        assert user.line_user_id == "U_NEW_001"
        assert user.id is not None and user.id > 0

    def test_returns_existing_user_on_second_call(self, db: sqlite3.Connection) -> None:
        u1 = get_or_create_user(db, "U_EXIST_001")
        u2 = get_or_create_user(db, "U_EXIST_001")
        assert u1.id == u2.id

    def test_no_duplicate_rows_in_db(self, db: sqlite3.Connection) -> None:
        get_or_create_user(db, "U_DUP_001")
        get_or_create_user(db, "U_DUP_001")
        count = db.execute(
            "SELECT COUNT(*) FROM users WHERE line_user_id=?", ("U_DUP_001",)
        ).fetchone()[0]
        assert count == 1

    def test_creates_user_settings_row_automatically(self, db: sqlite3.Connection) -> None:
        user = get_or_create_user(db, "U_SETTINGS_001")
        row = db.execute(
            "SELECT user_id FROM user_settings WHERE user_id=?", (user.id,)
        ).fetchone()
        assert row is not None

    def test_default_role_is_user(self, db: sqlite3.Connection) -> None:
        user = get_or_create_user(db, "U_ROLE_001")
        assert user.role == "user"

    def test_display_name_initially_none(self, db: sqlite3.Connection) -> None:
        user = get_or_create_user(db, "U_NAME_001")
        assert user.display_name is None

    def test_returns_user_model_instance(self, db: sqlite3.Connection) -> None:
        user = get_or_create_user(db, "U_TYPE_001")
        assert isinstance(user, User)


class TestGetUserById:
    def test_returns_user_when_found(self, db: sqlite3.Connection) -> None:
        created = get_or_create_user(db, "U_FIND_001")
        found = get_user_by_id(db, created.id)
        assert found is not None
        assert found.id == created.id
        assert found.line_user_id == "U_FIND_001"

    def test_returns_none_when_not_found(self, db: sqlite3.Connection) -> None:
        result = get_user_by_id(db, 99999)
        assert result is None

    def test_returns_user_model_instance(self, db: sqlite3.Connection) -> None:
        user = get_or_create_user(db, "U_FINDTYPE_001")
        found = get_user_by_id(db, user.id)
        assert isinstance(found, User)


class TestGetSettings:
    def test_returns_default_morning_time(self, db: sqlite3.Connection) -> None:
        user = get_or_create_user(db, "U_GSET_001")
        s = get_settings(db, user.id)
        assert s.morning_time == "07:30"

    def test_returns_default_evening_time(self, db: sqlite3.Connection) -> None:
        user = get_or_create_user(db, "U_GSET_002")
        s = get_settings(db, user.id)
        assert s.evening_time == "22:00"

    def test_returns_default_evening_enabled_true(self, db: sqlite3.Connection) -> None:
        user = get_or_create_user(db, "U_GSET_003")
        s = get_settings(db, user.id)
        assert s.evening_enabled is True

    def test_returns_default_timezone(self, db: sqlite3.Connection) -> None:
        user = get_or_create_user(db, "U_GSET_004")
        s = get_settings(db, user.id)
        assert s.timezone == "Asia/Tokyo"

    def test_returns_none_for_nonexistent_user(self, db: sqlite3.Connection) -> None:
        result = get_settings(db, 99999)
        assert result is None

    def test_returns_usersettings_model_instance(self, db: sqlite3.Connection) -> None:
        user = get_or_create_user(db, "U_GSETTYPE_001")
        s = get_settings(db, user.id)
        assert isinstance(s, UserSettings)


class TestUpdateSettings:
    def test_update_morning_time(self, db: sqlite3.Connection) -> None:
        user = get_or_create_user(db, "U_UTIME_001")
        update_settings(db, user.id, {"morning_time": "08:00"})
        s = get_settings(db, user.id)
        assert s.morning_time == "08:00"

    def test_update_evening_time(self, db: sqlite3.Connection) -> None:
        user = get_or_create_user(db, "U_UTIME_002")
        update_settings(db, user.id, {"evening_time": "21:30"})
        s = get_settings(db, user.id)
        assert s.evening_time == "21:30"

    def test_update_evening_enabled_to_false(self, db: sqlite3.Connection) -> None:
        user = get_or_create_user(db, "U_UENA_001")
        update_settings(db, user.id, {"evening_enabled": False})
        s = get_settings(db, user.id)
        assert s.evening_enabled is False

    def test_update_timezone(self, db: sqlite3.Connection) -> None:
        user = get_or_create_user(db, "U_UTZ_001")
        update_settings(db, user.id, {"timezone": "America/New_York"})
        s = get_settings(db, user.id)
        assert s.timezone == "America/New_York"

    def test_partial_update_preserves_other_fields(self, db: sqlite3.Connection) -> None:
        user = get_or_create_user(db, "U_PARTIAL_001")
        update_settings(db, user.id, {"morning_time": "09:00"})
        s = get_settings(db, user.id)
        assert s.evening_time == "22:00"
        assert s.evening_enabled is True
        assert s.timezone == "Asia/Tokyo"

    def test_invalid_time_format_raises_value_error(self, db: sqlite3.Connection) -> None:
        user = get_or_create_user(db, "U_BADFMT_001")
        with pytest.raises(ValueError, match="HH:MM"):
            update_settings(db, user.id, {"morning_time": "8am"})

    def test_invalid_time_no_db_update(self, db: sqlite3.Connection) -> None:
        """バリデーション失敗時はDBが変更されないこと。"""
        user = get_or_create_user(db, "U_NODIRTY_001")
        with pytest.raises(ValueError):
            update_settings(db, user.id, {"morning_time": "9:00"})
        s = get_settings(db, user.id)
        assert s.morning_time == "07:30"

    def test_unknown_field_raises_key_error(self, db: sqlite3.Connection) -> None:
        user = get_or_create_user(db, "U_BADKEY_001")
        with pytest.raises(KeyError):
            update_settings(db, user.id, {"unknown_field": "value"})

    def test_update_does_not_affect_other_user(self, db: sqlite3.Connection) -> None:
        """IDOR防止: 別ユーザーの設定が変わらないこと。"""
        u1 = get_or_create_user(db, "U_IDOR_001")
        u2 = get_or_create_user(db, "U_IDOR_002")
        update_settings(db, u1.id, {"morning_time": "06:00"})
        s2 = get_settings(db, u2.id)
        assert s2.morning_time == "07:30"

    def test_empty_updates_is_no_op(self, db: sqlite3.Connection) -> None:
        user = get_or_create_user(db, "U_NOOP_001")
        update_settings(db, user.id, {})
        s = get_settings(db, user.id)
        assert s.morning_time == "07:30"
