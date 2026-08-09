"""migration 001 (v1 → v2 multi-user schema) のテスト。

TDD: GREEN実装は migrations/runner.py:run_001()。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from migrations.runner import run_001
from tests.conftest import column_names, table_names


REQUIRED_TABLES_V2 = {
    "users",
    "medications",
    "user_medications",
    "user_settings",
    "servings",
    "serving_medications",
    "_migrations",
}


class TestCreatesV2Schema:
    """新規DBに対するスキーマ生成。"""

    def test_creates_all_v2_tables(self, empty_db: Path) -> None:
        run_001(empty_db, legacy_user_id=None)
        assert REQUIRED_TABLES_V2.issubset(table_names(empty_db))

    def test_servings_has_slot_column(self, empty_db: Path) -> None:
        run_001(empty_db, legacy_user_id=None)
        cols = column_names(empty_db, "servings")
        assert "slot" in cols, f"slot not in {cols}"

    def test_users_has_required_columns(self, empty_db: Path) -> None:
        run_001(empty_db, legacy_user_id=None)
        cols = column_names(empty_db, "users")
        for required in {
            "id",
            "line_user_id",
            "display_name",
            "contracted_clinic_id",
            "role",
            "created_at",
        }:
            assert required in cols, f"users.{required} missing"

    def test_user_settings_has_defaults(self, empty_db: Path) -> None:
        run_001(empty_db, legacy_user_id=None)
        cols = column_names(empty_db, "user_settings")
        for required in {
            "user_id",
            "morning_time",
            "evening_time",
            "evening_enabled",
            "timezone",
        }:
            assert required in cols


class TestServingsConstraints:
    """v2 servings の UNIQUE / FK / slot CHECK。"""

    def _seed_user(self, db_path: Path, line_user_id: str = "U_TEST") -> int:
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute(
                "INSERT INTO users (line_user_id, created_at) VALUES (?, datetime('now'))",
                (line_user_id,),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def test_morning_evening_can_coexist_same_date(self, empty_db: Path) -> None:
        run_001(empty_db, legacy_user_id=None)
        user_id = self._seed_user(empty_db)
        conn = sqlite3.connect(empty_db)
        try:
            conn.execute(
                "INSERT INTO servings (user_id, scheduled_date, slot) VALUES (?, ?, ?)",
                (user_id, "2026-05-06", "morning"),
            )
            conn.execute(
                "INSERT INTO servings (user_id, scheduled_date, slot) VALUES (?, ?, ?)",
                (user_id, "2026-05-06", "evening"),
            )
            conn.commit()
            count = conn.execute(
                "SELECT COUNT(*) FROM servings WHERE user_id=?", (user_id,)
            ).fetchone()[0]
            assert count == 2
        finally:
            conn.close()

    def test_same_user_date_slot_rejected(self, empty_db: Path) -> None:
        run_001(empty_db, legacy_user_id=None)
        user_id = self._seed_user(empty_db)
        conn = sqlite3.connect(empty_db)
        try:
            conn.execute(
                "INSERT INTO servings (user_id, scheduled_date, slot) VALUES (?, ?, ?)",
                (user_id, "2026-05-06", "morning"),
            )
            conn.commit()
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO servings (user_id, scheduled_date, slot) VALUES (?, ?, ?)",
                    (user_id, "2026-05-06", "morning"),
                )
                conn.commit()
        finally:
            conn.close()

    def test_invalid_slot_rejected(self, empty_db: Path) -> None:
        run_001(empty_db, legacy_user_id=None)
        user_id = self._seed_user(empty_db)
        conn = sqlite3.connect(empty_db)
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO servings (user_id, scheduled_date, slot) VALUES (?, ?, ?)",
                    (user_id, "2026-05-06", "midnight"),
                )
                conn.commit()
        finally:
            conn.close()


class TestV1Migration:
    """v1 既存データの v2 への移行。"""

    def test_legacy_user_row_inserted(self, v1_db: Path) -> None:
        run_001(v1_db, legacy_user_id="U_TEST_USER_001")
        conn = sqlite3.connect(v1_db)
        try:
            users = conn.execute("SELECT line_user_id FROM users").fetchall()
            assert len(users) == 1
            assert users[0][0] == "U_TEST_USER_001"
        finally:
            conn.close()

    def test_default_user_settings_inserted(self, v1_db: Path) -> None:
        run_001(v1_db, legacy_user_id="U_TEST_USER_001")
        conn = sqlite3.connect(v1_db)
        try:
            row = conn.execute(
                """SELECT morning_time, evening_time, evening_enabled, timezone
                   FROM user_settings"""
            ).fetchone()
            assert row == ("07:30", "22:00", 1, "Asia/Tokyo")
        finally:
            conn.close()

    def test_v1_servings_rows_preserved(self, v1_db: Path) -> None:
        """3行のv1データがすべて残ること。"""
        run_001(v1_db, legacy_user_id="U_TEST_USER_001")
        conn = sqlite3.connect(v1_db)
        try:
            rows = conn.execute(
                """SELECT scheduled_date, pushed_at, taken_at, slot
                   FROM servings ORDER BY scheduled_date"""
            ).fetchall()
            assert len(rows) == 3
            # 飲んだ日のデータ保持確認
            assert rows[0][0] == "2026-04-30"
            assert rows[0][1] == "2026-04-30T07:30:00"
            assert rows[0][2] == "2026-04-30T08:15:00"
            # 飲み忘れ (NULL)
            assert rows[2][2] is None
            # 全行 slot='morning' (v1 には slot 概念なし、全部朝として扱う)
            assert all(r[3] == "morning" for r in rows)
        finally:
            conn.close()

    def test_v1_user_id_remapped_to_users_id(self, v1_db: Path) -> None:
        """v1 の TEXT user_id が新 users.id (INTEGER) に紐付く。"""
        run_001(v1_db, legacy_user_id="U_TEST_USER_001")
        conn = sqlite3.connect(v1_db)
        try:
            # v1 は user_id TEXT。v2は INTEGER FK。サブクエリでJOIN確認
            row = conn.execute(
                """SELECT u.line_user_id
                   FROM servings s JOIN users u ON s.user_id = u.id
                   LIMIT 1"""
            ).fetchone()
            assert row is not None
            assert row[0] == "U_TEST_USER_001"
        finally:
            conn.close()

    def test_legacy_servings_v1_backup_kept(self, v1_db: Path) -> None:
        """servings_v1 という rollback 用テーブルが残る。"""
        run_001(v1_db, legacy_user_id="U_TEST_USER_001")
        tables = table_names(v1_db)
        assert "servings_v1" in tables


class TestIdempotency:
    """二度実行しても壊れない。"""

    def test_run_twice_no_error(self, empty_db: Path) -> None:
        run_001(empty_db, legacy_user_id=None)
        run_001(empty_db, legacy_user_id=None)  # should not raise
        assert REQUIRED_TABLES_V2.issubset(table_names(empty_db))

    def test_run_twice_no_duplicate_legacy_user(self, v1_db: Path) -> None:
        run_001(v1_db, legacy_user_id="U_TEST_USER_001")
        run_001(v1_db, legacy_user_id="U_TEST_USER_001")
        conn = sqlite3.connect(v1_db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            assert count == 1
        finally:
            conn.close()

    def test_migration_recorded(self, empty_db: Path) -> None:
        run_001(empty_db, legacy_user_id=None)
        conn = sqlite3.connect(empty_db)
        try:
            row = conn.execute(
                "SELECT name FROM _migrations WHERE name='001_multiuser'"
            ).fetchone()
            assert row is not None
        finally:
            conn.close()
