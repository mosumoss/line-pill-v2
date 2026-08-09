"""repositories/servings.py のテスト。

TDD: GREEN実装は repositories/servings.py。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from migrations.runner import run_001, run_002
from repositories.servings import (
    Serving,
    get_or_create_serving,
    get_serving,
    list_servings,
    mark_taken,
)
from repositories.users import get_or_create_user


@pytest.fixture
def db(empty_db: Path) -> sqlite3.Connection:
    """Migration 001 + 002 適用済み DB への接続。"""
    run_001(empty_db)
    run_002(empty_db)
    conn = sqlite3.connect(empty_db)
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


@pytest.fixture
def user_id(db: sqlite3.Connection) -> int:
    return get_or_create_user(db, "U_SRV_001").id


@pytest.fixture
def user2_id(db: sqlite3.Connection) -> int:
    return get_or_create_user(db, "U_SRV_002").id


class TestGetOrCreateServing:
    def test_creates_morning_serving(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        s = get_or_create_serving(db, user_id=user_id, date="2026-05-06", slot="morning")
        assert s.user_id == user_id
        assert s.scheduled_date == "2026-05-06"
        assert s.slot == "morning"

    def test_creates_evening_serving(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        s = get_or_create_serving(db, user_id=user_id, date="2026-05-06", slot="evening")
        assert s.slot == "evening"

    def test_returns_same_id_on_second_call(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        s1 = get_or_create_serving(db, user_id=user_id, date="2026-05-06", slot="morning")
        s2 = get_or_create_serving(db, user_id=user_id, date="2026-05-06", slot="morning")
        assert s1.id == s2.id

    def test_no_duplicate_row_in_db(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        get_or_create_serving(db, user_id=user_id, date="2026-05-06", slot="morning")
        get_or_create_serving(db, user_id=user_id, date="2026-05-06", slot="morning")
        count = db.execute(
            "SELECT COUNT(*) FROM servings WHERE user_id=? AND scheduled_date=? AND slot=?",
            (user_id, "2026-05-06", "morning"),
        ).fetchone()[0]
        assert count == 1

    def test_morning_and_evening_can_coexist(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        m = get_or_create_serving(db, user_id=user_id, date="2026-05-06", slot="morning")
        e = get_or_create_serving(db, user_id=user_id, date="2026-05-06", slot="evening")
        assert m.id != e.id

    def test_invalid_slot_raises_value_error(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        with pytest.raises(ValueError, match="slot"):
            get_or_create_serving(db, user_id=user_id, date="2026-05-06", slot="midnight")

    def test_taken_at_initially_none(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        s = get_or_create_serving(db, user_id=user_id, date="2026-05-06", slot="morning")
        assert s.taken_at is None

    def test_returns_serving_model_instance(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        s = get_or_create_serving(db, user_id=user_id, date="2026-05-06", slot="morning")
        assert isinstance(s, Serving)


class TestGetServing:
    def test_returns_serving_by_id(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        created = get_or_create_serving(
            db, user_id=user_id, date="2026-05-06", slot="morning"
        )
        found = get_serving(db, serving_id=created.id, user_id=user_id)
        assert found is not None
        assert found.id == created.id

    def test_returns_none_when_not_found(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        result = get_serving(db, serving_id=99999, user_id=user_id)
        assert result is None

    def test_idor_different_user_returns_none(
        self, db: sqlite3.Connection, user_id: int, user2_id: int
    ) -> None:
        """IDOR防止: 他ユーザーの serving_id は取得できないこと。"""
        s = get_or_create_serving(
            db, user_id=user2_id, date="2026-05-06", slot="morning"
        )
        result = get_serving(db, serving_id=s.id, user_id=user_id)
        assert result is None


class TestMarkTaken:
    def test_marks_taken_at(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        s = get_or_create_serving(db, user_id=user_id, date="2026-05-06", slot="morning")
        result = mark_taken(db, user_id=user_id, serving_id=s.id)
        assert result is True
        updated = get_serving(db, serving_id=s.id, user_id=user_id)
        assert updated.taken_at is not None

    def test_returns_false_when_already_taken(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        """TOCTOU防止: 二重 mark_taken は False を返す。"""
        s = get_or_create_serving(db, user_id=user_id, date="2026-05-06", slot="morning")
        mark_taken(db, user_id=user_id, serving_id=s.id)
        result = mark_taken(db, user_id=user_id, serving_id=s.id)
        assert result is False

    def test_taken_at_not_overwritten_on_second_call(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        s = get_or_create_serving(db, user_id=user_id, date="2026-05-06", slot="morning")
        mark_taken(db, user_id=user_id, serving_id=s.id)
        first_taken = get_serving(db, serving_id=s.id, user_id=user_id).taken_at
        mark_taken(db, user_id=user_id, serving_id=s.id)
        second_taken = get_serving(db, serving_id=s.id, user_id=user_id).taken_at
        assert first_taken == second_taken

    def test_idor_cannot_mark_other_users_serving(
        self, db: sqlite3.Connection, user_id: int, user2_id: int
    ) -> None:
        """IDOR防止: 他ユーザーの serving を mark_taken できないこと。"""
        s = get_or_create_serving(
            db, user_id=user2_id, date="2026-05-06", slot="morning"
        )
        result = mark_taken(db, user_id=user_id, serving_id=s.id)
        assert result is False
        untouched = get_serving(db, serving_id=s.id, user_id=user2_id)
        assert untouched.taken_at is None

    def test_returns_false_for_nonexistent_serving(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        result = mark_taken(db, user_id=user_id, serving_id=99999)
        assert result is False


class TestListServings:
    def test_returns_servings_in_date_range(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        get_or_create_serving(db, user_id=user_id, date="2026-05-01", slot="morning")
        get_or_create_serving(db, user_id=user_id, date="2026-05-03", slot="morning")
        get_or_create_serving(db, user_id=user_id, date="2026-05-10", slot="morning")
        result = list_servings(
            db, user_id=user_id, from_date="2026-05-01", to_date="2026-05-05"
        )
        assert len(result) == 2

    def test_returns_empty_when_no_servings(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        result = list_servings(
            db, user_id=user_id, from_date="2026-05-01", to_date="2026-05-07"
        )
        assert result == []

    def test_ordered_by_date_asc(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        get_or_create_serving(db, user_id=user_id, date="2026-05-03", slot="morning")
        get_or_create_serving(db, user_id=user_id, date="2026-05-01", slot="morning")
        result = list_servings(
            db, user_id=user_id, from_date="2026-05-01", to_date="2026-05-05"
        )
        dates = [s.scheduled_date for s in result]
        assert dates == sorted(dates)

    def test_does_not_return_other_users_servings(
        self, db: sqlite3.Connection, user_id: int, user2_id: int
    ) -> None:
        """IDOR防止: 他ユーザーの serving が含まれないこと。"""
        get_or_create_serving(db, user_id=user2_id, date="2026-05-01", slot="morning")
        result = list_servings(
            db, user_id=user_id, from_date="2026-05-01", to_date="2026-05-07"
        )
        assert result == []

    def test_includes_both_slots_in_range(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        get_or_create_serving(db, user_id=user_id, date="2026-05-06", slot="morning")
        get_or_create_serving(db, user_id=user_id, date="2026-05-06", slot="evening")
        result = list_servings(
            db, user_id=user_id, from_date="2026-05-06", to_date="2026-05-06"
        )
        slots = {s.slot for s in result}
        assert slots == {"morning", "evening"}

    def test_returns_serving_model_instances(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        get_or_create_serving(db, user_id=user_id, date="2026-05-06", slot="morning")
        result = list_servings(
            db, user_id=user_id, from_date="2026-05-06", to_date="2026-05-06"
        )
        assert all(isinstance(s, Serving) for s in result)
