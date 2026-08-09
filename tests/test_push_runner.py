"""push_runner.py (per-user push dispatcher) のテスト。

TDD: GREEN実装は push_runner.py + line_api.py + repositories/servings.set_pushed_at。
freezegun で時刻を固定し、push_fn を差し替えてテストする。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from migrations.runner import run_001, run_002
from push_runner import run_tick
from repositories.servings import get_or_create_serving, get_serving, set_pushed_at
from repositories.users import get_or_create_user, update_settings


# ---------- Fixtures ----------

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Migration 001 + 002 適用済み DB パス。"""
    path = tmp_path / "test_push.db"
    run_001(path)
    run_002(path)
    return path


@pytest.fixture
def db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


# UTC 07:30 JST = 2026-05-06 07:30+09:00 → UTC 2026-05-05 22:30:00
MORNING_UTC = datetime(2026, 5, 5, 22, 30, 0, tzinfo=timezone.utc)
# UTC 13:00 JST = 2026-05-06 22:00+09:00 → UTC 2026-05-06 13:00:00
EVENING_UTC = datetime(2026, 5, 6, 13, 0, 0, tzinfo=timezone.utc)


# ---------- set_pushed_at (servings repo extension) ----------

class TestSetPushedAt:
    def test_sets_pushed_at_for_unpushed_serving(
        self, db: sqlite3.Connection, db_path: Path
    ) -> None:
        user = get_or_create_user(db, "U_PUSH_001")
        s = get_or_create_serving(db, user_id=user.id, date="2026-05-06", slot="morning")
        result = set_pushed_at(db, serving_id=s.id, user_id=user.id)
        assert result is True
        updated = get_serving(db, serving_id=s.id, user_id=user.id)
        assert updated.pushed_at is not None

    def test_returns_false_when_already_pushed(
        self, db: sqlite3.Connection, db_path: Path
    ) -> None:
        user = get_or_create_user(db, "U_PUSH_002")
        s = get_or_create_serving(db, user_id=user.id, date="2026-05-06", slot="morning")
        set_pushed_at(db, serving_id=s.id, user_id=user.id)
        result = set_pushed_at(db, serving_id=s.id, user_id=user.id)
        assert result is False

    def test_idor_different_user_returns_false(
        self, db: sqlite3.Connection, db_path: Path
    ) -> None:
        u1 = get_or_create_user(db, "U_PUSH_003")
        u2 = get_or_create_user(db, "U_PUSH_004")
        s = get_or_create_serving(db, user_id=u2.id, date="2026-05-06", slot="morning")
        result = set_pushed_at(db, serving_id=s.id, user_id=u1.id)
        assert result is False


# ---------- run_tick ----------

class TestRunTickMorning:
    def test_notifies_user_at_morning_time(
        self, db_path: Path, db: sqlite3.Connection
    ) -> None:
        get_or_create_user(db, "U_TICK_001")
        notified: list[tuple[str, str]] = []

        with freeze_time(MORNING_UTC):
            result = run_tick(
                db_path, datetime.now(tz=timezone.utc),
                push_fn=lambda uid, slot: notified.append((uid, slot)),
            )

        assert "U_TICK_001" in result
        assert ("U_TICK_001", "morning") in notified

    def test_creates_serving_on_push(
        self, db_path: Path, db: sqlite3.Connection
    ) -> None:
        user = get_or_create_user(db, "U_TICK_002")

        with freeze_time(MORNING_UTC):
            run_tick(
                db_path, datetime.now(tz=timezone.utc),
                push_fn=lambda *_: None,
            )

        jst = ZoneInfo("Asia/Tokyo")
        today_jst = MORNING_UTC.astimezone(jst).date().isoformat()
        s = get_serving(
            db,
            serving_id=db.execute(
                "SELECT id FROM servings WHERE user_id=? AND slot='morning'",
                (user.id,),
            ).fetchone()[0],
            user_id=user.id,
        )
        assert s is not None
        assert s.pushed_at is not None

    def test_does_not_push_at_non_push_time(
        self, db_path: Path, db: sqlite3.Connection
    ) -> None:
        get_or_create_user(db, "U_TICK_003")
        # UTC 12:00 → JST 21:00 (どちらの通知時刻にも一致しない)
        off_time = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)
        notified: list[str] = []

        run_tick(
            db_path, off_time,
            push_fn=lambda uid, slot: notified.append(uid),
        )

        assert "U_TICK_003" not in notified


class TestRunTickEvening:
    def test_notifies_user_at_evening_time(
        self, db_path: Path, db: sqlite3.Connection
    ) -> None:
        get_or_create_user(db, "U_TICK_EVEN_001")
        notified: list[tuple[str, str]] = []

        with freeze_time(EVENING_UTC):
            run_tick(
                db_path, datetime.now(tz=timezone.utc),
                push_fn=lambda uid, slot: notified.append((uid, slot)),
            )

        assert ("U_TICK_EVEN_001", "evening") in notified

    def test_skips_evening_when_evening_disabled(
        self, db_path: Path, db: sqlite3.Connection
    ) -> None:
        user = get_or_create_user(db, "U_TICK_EVEN_002")
        update_settings(db, user.id, {"evening_enabled": False})
        notified: list[str] = []

        with freeze_time(EVENING_UTC):
            run_tick(
                db_path, datetime.now(tz=timezone.utc),
                push_fn=lambda uid, slot: notified.append(uid),
            )

        assert "U_TICK_EVEN_002" not in notified


class TestRunTickIdempotency:
    def test_no_duplicate_push_on_second_tick(
        self, db_path: Path, db: sqlite3.Connection
    ) -> None:
        """同じ分に2回 tick が来ても1回しかプッシュしない (pushed_at 設定済みでスキップ)。"""
        get_or_create_user(db, "U_TICK_IDEM_001")
        call_count = 0

        def counting_push(uid: str, slot: str) -> None:
            nonlocal call_count
            call_count += 1

        with freeze_time(MORNING_UTC):
            now = datetime.now(tz=timezone.utc)
            run_tick(db_path, now, push_fn=counting_push)
            run_tick(db_path, now, push_fn=counting_push)

        assert call_count == 1


class TestRunTickMultiUser:
    def test_notifies_multiple_users(
        self, db_path: Path, db: sqlite3.Connection
    ) -> None:
        get_or_create_user(db, "U_MULTI_001")
        get_or_create_user(db, "U_MULTI_002")
        notified: list[str] = []

        with freeze_time(MORNING_UTC):
            run_tick(
                db_path, datetime.now(tz=timezone.utc),
                push_fn=lambda uid, slot: notified.append(uid),
            )

        assert "U_MULTI_001" in notified
        assert "U_MULTI_002" in notified

    def test_custom_morning_time_per_user(
        self, db_path: Path, db: sqlite3.Connection
    ) -> None:
        """ユーザーごとに朝の通知時刻が異なる場合。"""
        u1 = get_or_create_user(db, "U_CUSTOM_001")
        u2 = get_or_create_user(db, "U_CUSTOM_002")
        # u1: 朝 06:00 JST → UTC 21:00
        # u2: 朝 07:30 JST → UTC 22:30 (デフォルト)
        update_settings(db, u1.id, {"morning_time": "06:00"})

        # UTC 21:00 → JST 06:00 (u1 の朝)
        tick_time = datetime(2026, 5, 5, 21, 0, 0, tzinfo=timezone.utc)
        notified: list[str] = []

        run_tick(
            db_path, tick_time,
            push_fn=lambda uid, slot: notified.append(uid),
        )

        assert "U_CUSTOM_001" in notified
        assert "U_CUSTOM_002" not in notified  # u2 の朝は 07:30 JST
