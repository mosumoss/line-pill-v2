"""repositories/medications.py のテスト。

TDD: GREEN実装は repositories/medications.py。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from migrations.runner import run_001, run_002
from repositories.medications import (
    Medication,
    UserMedication,
    add_user_medication,
    get_medication_by_id,
    list_preset_medications,
    list_user_medications,
    remove_user_medication,
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
    return get_or_create_user(db, "U_MED_001").id


@pytest.fixture
def user2_id(db: sqlite3.Connection) -> int:
    return get_or_create_user(db, "U_MED_002").id


class TestListPresetMedications:
    def test_returns_six_presets(self, db: sqlite3.Connection) -> None:
        meds = list_preset_medications(db)
        assert len(meds) == 6

    def test_returns_medication_model_instances(self, db: sqlite3.Connection) -> None:
        meds = list_preset_medications(db)
        assert all(isinstance(m, Medication) for m in meds)

    def test_all_are_preset(self, db: sqlite3.Connection) -> None:
        meds = list_preset_medications(db)
        assert all(m.is_preset for m in meds)

    def test_kinds_are_valid(self, db: sqlite3.Connection) -> None:
        valid_kinds = {"topical", "oral", "supplement", "other"}
        meds = list_preset_medications(db)
        assert all(m.kind in valid_kinds for m in meds)

    def test_no_brand_names(self, db: sqlite3.Connection) -> None:
        forbidden = {"フィンペシア", "プロペシア", "ザガーロ", "ミノタブ"}
        meds = list_preset_medications(db)
        names = {m.name for m in meds}
        assert not names & forbidden


class TestGetMedicationById:
    def test_returns_medication_when_found(self, db: sqlite3.Connection) -> None:
        presets = list_preset_medications(db)
        first = presets[0]
        found = get_medication_by_id(db, first.id)
        assert found is not None
        assert found.id == first.id
        assert found.name == first.name

    def test_returns_none_when_not_found(self, db: sqlite3.Connection) -> None:
        result = get_medication_by_id(db, 99999)
        assert result is None


class TestAddUserMedication:
    def test_add_preset_morning(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        med_id = list_preset_medications(db)[0].id
        add_user_medication(db, user_id=user_id, medication_id=med_id, slot="morning")
        meds = list_user_medications(db, user_id=user_id, slot="morning")
        assert any(m.medication_id == med_id for m in meds)

    def test_add_preset_evening(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        med_id = list_preset_medications(db)[0].id
        add_user_medication(db, user_id=user_id, medication_id=med_id, slot="evening")
        meds = list_user_medications(db, user_id=user_id, slot="evening")
        assert any(m.medication_id == med_id for m in meds)

    def test_add_same_med_twice_is_idempotent(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        med_id = list_preset_medications(db)[0].id
        add_user_medication(db, user_id=user_id, medication_id=med_id, slot="morning")
        add_user_medication(db, user_id=user_id, medication_id=med_id, slot="morning")
        meds = list_user_medications(db, user_id=user_id, slot="morning")
        assert sum(1 for m in meds if m.medication_id == med_id) == 1

    def test_add_same_med_morning_and_evening(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        med_id = list_preset_medications(db)[0].id
        add_user_medication(db, user_id=user_id, medication_id=med_id, slot="morning")
        add_user_medication(db, user_id=user_id, medication_id=med_id, slot="evening")
        morning = list_user_medications(db, user_id=user_id, slot="morning")
        evening = list_user_medications(db, user_id=user_id, slot="evening")
        assert any(m.medication_id == med_id for m in morning)
        assert any(m.medication_id == med_id for m in evening)

    def test_invalid_slot_raises_value_error(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        med_id = list_preset_medications(db)[0].id
        with pytest.raises(ValueError, match="slot"):
            add_user_medication(
                db, user_id=user_id, medication_id=med_id, slot="midnight"
            )

    def test_nonexistent_medication_raises_error(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        with pytest.raises(Exception):
            add_user_medication(db, user_id=user_id, medication_id=99999, slot="morning")


class TestListUserMedications:
    def test_returns_only_enabled(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        meds = list_preset_medications(db)
        add_user_medication(db, user_id=user_id, medication_id=meds[0].id, slot="morning")
        add_user_medication(db, user_id=user_id, medication_id=meds[1].id, slot="morning")
        result = list_user_medications(db, user_id=user_id, slot="morning")
        assert len(result) == 2
        assert all(m.enabled for m in result)

    def test_empty_when_no_medications_added(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        result = list_user_medications(db, user_id=user_id, slot="morning")
        assert result == []

    def test_slot_filter_morning(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        presets = list_preset_medications(db)
        add_user_medication(db, user_id=user_id, medication_id=presets[0].id, slot="morning")
        add_user_medication(db, user_id=user_id, medication_id=presets[1].id, slot="evening")
        morning = list_user_medications(db, user_id=user_id, slot="morning")
        assert len(morning) == 1
        assert morning[0].medication_id == presets[0].id

    def test_slot_filter_evening(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        presets = list_preset_medications(db)
        add_user_medication(db, user_id=user_id, medication_id=presets[0].id, slot="morning")
        add_user_medication(db, user_id=user_id, medication_id=presets[1].id, slot="evening")
        evening = list_user_medications(db, user_id=user_id, slot="evening")
        assert len(evening) == 1
        assert evening[0].medication_id == presets[1].id

    def test_returns_user_medication_model_instances(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        presets = list_preset_medications(db)
        add_user_medication(db, user_id=user_id, medication_id=presets[0].id, slot="morning")
        result = list_user_medications(db, user_id=user_id, slot="morning")
        assert all(isinstance(m, UserMedication) for m in result)

    def test_does_not_return_other_users_medications(
        self, db: sqlite3.Connection, user_id: int, user2_id: int
    ) -> None:
        """IDOR防止: 他ユーザーの薬が含まれないこと。"""
        presets = list_preset_medications(db)
        add_user_medication(db, user_id=user2_id, medication_id=presets[0].id, slot="morning")
        result = list_user_medications(db, user_id=user_id, slot="morning")
        assert result == []


class TestRemoveUserMedication:
    def test_remove_disables_medication(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        med_id = list_preset_medications(db)[0].id
        add_user_medication(db, user_id=user_id, medication_id=med_id, slot="morning")
        remove_user_medication(db, user_id=user_id, medication_id=med_id, slot="morning")
        result = list_user_medications(db, user_id=user_id, slot="morning")
        assert not any(m.medication_id == med_id for m in result)

    def test_remove_nonexistent_is_no_op(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        remove_user_medication(db, user_id=user_id, medication_id=99999, slot="morning")

    def test_remove_does_not_affect_other_slot(
        self, db: sqlite3.Connection, user_id: int
    ) -> None:
        med_id = list_preset_medications(db)[0].id
        add_user_medication(db, user_id=user_id, medication_id=med_id, slot="morning")
        add_user_medication(db, user_id=user_id, medication_id=med_id, slot="evening")
        remove_user_medication(db, user_id=user_id, medication_id=med_id, slot="morning")
        evening = list_user_medications(db, user_id=user_id, slot="evening")
        assert any(m.medication_id == med_id for m in evening)

    def test_remove_does_not_affect_other_user(
        self, db: sqlite3.Connection, user_id: int, user2_id: int
    ) -> None:
        """IDOR防止: 他ユーザーの薬を削除できないこと。"""
        med_id = list_preset_medications(db)[0].id
        add_user_medication(db, user_id=user2_id, medication_id=med_id, slot="morning")
        remove_user_medication(db, user_id=user_id, medication_id=med_id, slot="morning")
        result = list_user_medications(db, user_id=user2_id, slot="morning")
        assert any(m.medication_id == med_id for m in result)
