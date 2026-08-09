"""users リポジトリ — users / user_settings テーブルのデータアクセス層。

すべてのクエリは user_id でスコープされ IDOR を防止する。
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass


# ---------- Models ----------

@dataclass(frozen=True)
class User:
    id: int
    line_user_id: str
    display_name: str | None
    contracted_clinic_id: int | None
    role: str
    created_at: str


@dataclass(frozen=True)
class UserSettings:
    user_id: int
    morning_time: str
    evening_time: str
    evening_enabled: bool
    timezone: str
    reminder_mode: str  # 'off' | 'interval' | 'fixed'
    reminder_interval_hours: int
    reminder_times: str  # CSV 'HH:MM,HH:MM'
    updated_at: str


# ---------- Validation ----------

_HH_MM_RE = re.compile(r"^\d{2}:\d{2}$")

_ALLOWED_SETTINGS_KEYS = frozenset({
    "morning_time",
    "evening_time",
    "evening_enabled",
    "timezone",
    "reminder_mode",
    "reminder_interval_hours",
    "reminder_times",
})

_TIME_FIELDS = frozenset({"morning_time", "evening_time"})

_VALID_REMINDER_MODES = frozenset({"off", "interval", "fixed"})


def _validate_updates(updates: dict[str, object]) -> None:
    """更新dictのキーと値を事前検証。DB書き込み前に全件確認する。"""
    for key, value in updates.items():
        if key not in _ALLOWED_SETTINGS_KEYS:
            raise KeyError(f"Unknown settings field: {key!r}")
        if key in _TIME_FIELDS:
            s = str(value)
            if not _HH_MM_RE.match(s):
                raise ValueError(
                    f"Invalid time format {s!r}: expected HH:MM (e.g. '07:30')"
                )
        elif key == "reminder_mode":
            if str(value) not in _VALID_REMINDER_MODES:
                raise ValueError(
                    f"Invalid reminder_mode {value!r}: expected one of {sorted(_VALID_REMINDER_MODES)}"
                )
        elif key == "reminder_interval_hours":
            try:
                n = int(value)  # type: ignore[arg-type]
            except (TypeError, ValueError) as exc:
                raise ValueError(f"reminder_interval_hours must be int, got {value!r}") from exc
            if n < 0 or n > 24:
                raise ValueError(f"reminder_interval_hours must be 0..24, got {n}")
        elif key == "reminder_times":
            s = str(value)
            if s:
                for t in s.split(","):
                    t = t.strip()
                    if not _HH_MM_RE.match(t):
                        raise ValueError(
                            f"Invalid reminder_times entry {t!r}: expected 'HH:MM'"
                        )


# ---------- Row → Model helpers ----------

def _row_to_user(row: tuple) -> User:
    return User(
        id=row[0],
        line_user_id=row[1],
        display_name=row[2],
        contracted_clinic_id=row[3],
        role=row[4],
        created_at=row[5],
    )


def _row_to_settings(row: tuple) -> UserSettings:
    return UserSettings(
        user_id=row[0],
        morning_time=row[1],
        evening_time=row[2],
        evening_enabled=bool(row[3]),
        timezone=row[4],
        reminder_mode=row[5],
        reminder_interval_hours=int(row[6]),
        reminder_times=row[7] or "",
        updated_at=row[8],
    )


# ---------- Public API ----------

def get_or_create_user(conn: sqlite3.Connection, line_user_id: str) -> User:
    """users 行と user_settings 行を idempotent に作成し User を返す。"""
    conn.execute(
        "INSERT OR IGNORE INTO users (line_user_id) VALUES (?)",
        (line_user_id,),
    )
    row = conn.execute(
        "SELECT id, line_user_id, display_name, contracted_clinic_id, role, created_at "
        "FROM users WHERE line_user_id=?",
        (line_user_id,),
    ).fetchone()
    conn.execute(
        "INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)",
        (row[0],),
    )
    conn.commit()
    return _row_to_user(row)


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> User | None:
    """integer PK で users を取得。存在しなければ None。"""
    row = conn.execute(
        "SELECT id, line_user_id, display_name, contracted_clinic_id, role, created_at "
        "FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_user(row)


def get_settings(conn: sqlite3.Connection, user_id: int) -> UserSettings | None:
    """user_id に紐づく user_settings を返す。存在しなければ None。"""
    row = conn.execute(
        "SELECT user_id, morning_time, evening_time, evening_enabled, timezone, "
        "reminder_mode, reminder_interval_hours, reminder_times, updated_at "
        "FROM user_settings WHERE user_id=?",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_settings(row)


def update_settings(
    conn: sqlite3.Connection,
    user_id: int,
    updates: dict[str, object],
) -> None:
    """user_settings の指定フィールドを更新する。

    Args:
        conn: DB接続
        user_id: 更新対象ユーザーの内部ID。WHERE user_id=? でスコープ (IDOR防止)
        updates: 更新するフィールド名と値のdict

    Raises:
        KeyError: 許可されていないフィールド名
        ValueError: 時刻フォーマット不正 (HH:MM 以外)
    """
    if not updates:
        return

    _validate_updates(updates)  # 全件バリデーション後にDB操作

    # キーは _ALLOWED_SETTINGS_KEYS で検証済みなので安全に展開できる
    set_clauses = ", ".join(f"{k}=?" for k in updates)
    set_clauses += ", updated_at=datetime('now')"
    values = list(updates.values()) + [user_id]
    conn.execute(
        f"UPDATE user_settings SET {set_clauses} WHERE user_id=?",
        values,
    )
    conn.commit()
