"""medications リポジトリ — medications / user_medications テーブルのデータアクセス層。

すべてのユーザー向けクエリは user_id でスコープされ IDOR を防止する。
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

_VALID_SLOTS = frozenset({"morning", "evening"})


# ---------- Models ----------

@dataclass(frozen=True)
class Medication:
    id: int
    name: str
    kind: str
    is_preset: bool
    created_by_user_id: int | None


@dataclass(frozen=True)
class UserMedication:
    id: int
    user_id: int
    medication_id: int
    slot: str
    enabled: bool


# ---------- Row → Model helpers ----------

def _row_to_medication(row: tuple) -> Medication:
    return Medication(
        id=row[0],
        name=row[1],
        kind=row[2],
        is_preset=bool(row[3]),
        created_by_user_id=row[4],
    )


def _row_to_user_medication(row: tuple) -> UserMedication:
    return UserMedication(
        id=row[0],
        user_id=row[1],
        medication_id=row[2],
        slot=row[3],
        enabled=bool(row[4]),
    )


# ---------- Public API ----------

def list_preset_medications(conn: sqlite3.Connection) -> list[Medication]:
    """is_preset=1 の薬一覧を id 順で返す。"""
    rows = conn.execute(
        "SELECT id, name, kind, is_preset, created_by_user_id "
        "FROM medications WHERE is_preset=1 ORDER BY id"
    ).fetchall()
    return [_row_to_medication(r) for r in rows]


def get_medication_by_id(
    conn: sqlite3.Connection, medication_id: int
) -> Medication | None:
    """id で medications を取得。存在しなければ None。"""
    row = conn.execute(
        "SELECT id, name, kind, is_preset, created_by_user_id "
        "FROM medications WHERE id=?",
        (medication_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_medication(row)


def list_user_medications(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    slot: str,
) -> list[UserMedication]:
    """指定ユーザー・スロットの有効な user_medications を返す。

    IDOR防止: WHERE user_id=? で必ずスコープする。
    """
    rows = conn.execute(
        "SELECT id, user_id, medication_id, slot, enabled "
        "FROM user_medications "
        "WHERE user_id=? AND slot=? AND enabled=1 "
        "ORDER BY id",
        (user_id, slot),
    ).fetchall()
    return [_row_to_user_medication(r) for r in rows]


def add_user_medication(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    medication_id: int,
    slot: str,
) -> None:
    """user_medications に行を追加 (idempotent: 既存なら enabled=1 に復元)。

    Raises:
        ValueError: slot が 'morning' / 'evening' 以外
        sqlite3.IntegrityError: medication_id が存在しない (FK 違反)
    """
    if slot not in _VALID_SLOTS:
        raise ValueError(f"Invalid slot {slot!r}: must be one of {sorted(_VALID_SLOTS)}")

    conn.execute(
        """
        INSERT INTO user_medications (user_id, medication_id, slot, enabled)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(user_id, medication_id, slot) DO UPDATE SET enabled=1
        """,
        (user_id, medication_id, slot),
    )
    conn.commit()


def remove_user_medication(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    medication_id: int,
    slot: str,
) -> None:
    """user_medications を論理削除 (enabled=0)。

    IDOR防止: WHERE user_id=? でスコープ。
    存在しない行への操作は no-op。
    """
    conn.execute(
        "UPDATE user_medications SET enabled=0 "
        "WHERE user_id=? AND medication_id=? AND slot=?",
        (user_id, medication_id, slot),
    )
    conn.commit()
