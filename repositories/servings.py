"""servings リポジトリ — servings テーブルのデータアクセス層。

すべてのクエリは user_id でスコープされ IDOR を防止する。
mark_taken は WHERE taken_at IS NULL の原子的 UPDATE で TOCTOU を防止する。
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

_VALID_SLOTS = frozenset({"morning", "evening"})


# ---------- Model ----------

@dataclass(frozen=True)
class Serving:
    id: int
    user_id: int
    scheduled_date: str
    slot: str
    pushed_at: str | None
    reminded_at: str | None
    taken_at: str | None


# ---------- Row → Model ----------

def _row_to_serving(row: tuple) -> Serving:
    return Serving(
        id=row[0],
        user_id=row[1],
        scheduled_date=row[2],
        slot=row[3],
        pushed_at=row[4],
        reminded_at=row[5],
        taken_at=row[6],
    )


# ---------- Public API ----------

def get_or_create_serving(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    date: str,
    slot: str,
) -> Serving:
    """指定ユーザー・日付・スロットの serving を取得または作成する。

    Raises:
        ValueError: slot が 'morning' / 'evening' 以外
    """
    if slot not in _VALID_SLOTS:
        raise ValueError(f"Invalid slot {slot!r}: must be one of {sorted(_VALID_SLOTS)}")

    conn.execute(
        """
        INSERT OR IGNORE INTO servings (user_id, scheduled_date, slot)
        VALUES (?, ?, ?)
        """,
        (user_id, date, slot),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, user_id, scheduled_date, slot, pushed_at, reminded_at, taken_at "
        "FROM servings WHERE user_id=? AND scheduled_date=? AND slot=?",
        (user_id, date, slot),
    ).fetchone()
    return _row_to_serving(row)


def get_serving(
    conn: sqlite3.Connection,
    *,
    serving_id: int,
    user_id: int,
) -> Serving | None:
    """serving_id で取得。user_id でスコープ (IDOR防止)。存在しなければ None。"""
    row = conn.execute(
        "SELECT id, user_id, scheduled_date, slot, pushed_at, reminded_at, taken_at "
        "FROM servings WHERE id=? AND user_id=?",
        (serving_id, user_id),
    ).fetchone()
    if row is None:
        return None
    return _row_to_serving(row)


def mark_taken(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    serving_id: int,
) -> bool:
    """serving を服薬済みにする。

    TOCTOU防止: WHERE taken_at IS NULL の原子的 UPDATE を使用。
    IDOR防止: WHERE user_id=? でスコープ。

    Returns:
        True: 更新成功 (未服薬 → 服薬済み)
        False: 既に服薬済み、存在しない、または他ユーザーの serving
    """
    cur = conn.execute(
        "UPDATE servings SET taken_at=datetime('now') "
        "WHERE id=? AND user_id=? AND taken_at IS NULL",
        (serving_id, user_id),
    )
    conn.commit()
    return cur.rowcount == 1


def set_pushed_at(
    conn: sqlite3.Connection,
    *,
    serving_id: int,
    user_id: int,
) -> bool:
    """serving の pushed_at を現在時刻にセットする。

    IDOR防止: WHERE user_id=? でスコープ。
    pushed_at が既にセットされている場合は no-op で False を返す。

    Returns:
        True: セット成功 (未プッシュ → プッシュ済み)
        False: 既にプッシュ済み、存在しない、または他ユーザーの serving
    """
    cur = conn.execute(
        "UPDATE servings SET pushed_at=datetime('now') "
        "WHERE id=? AND user_id=? AND pushed_at IS NULL",
        (serving_id, user_id),
    )
    conn.commit()
    return cur.rowcount == 1


def set_reminded_at(
    conn: sqlite3.Connection,
    *,
    serving_id: int,
    user_id: int,
) -> bool:
    """serving の reminded_at を現在時刻にセットする (リマインダー送信記録)。

    IDOR防止: WHERE user_id=? でスコープ。
    既に taken_at がセットされている場合は何もしない (服用済みなのでリマインダー不要)。

    Returns:
        True: セット成功
        False: 既に服用済み or 他ユーザーの serving
    """
    cur = conn.execute(
        "UPDATE servings SET reminded_at=datetime('now') "
        "WHERE id=? AND user_id=? AND taken_at IS NULL",
        (serving_id, user_id),
    )
    conn.commit()
    return cur.rowcount == 1


def list_servings(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    from_date: str,
    to_date: str,
) -> list[Serving]:
    """指定ユーザーの日付範囲内の serving を日付昇順で返す。

    IDOR防止: WHERE user_id=? でスコープ。
    """
    rows = conn.execute(
        "SELECT id, user_id, scheduled_date, slot, pushed_at, reminded_at, taken_at "
        "FROM servings "
        "WHERE user_id=? AND scheduled_date BETWEEN ? AND ? "
        "ORDER BY scheduled_date ASC, slot ASC",
        (user_id, from_date, to_date),
    ).fetchall()
    return [_row_to_serving(r) for r in rows]
