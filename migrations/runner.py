"""DB マイグレーション実行ランナー。

公開関数:
- run_001(db_path, legacy_user_id=None) — v1→v2 multi-user スキーマ
- run_002(db_path) — preset medications 投入
- run_all(db_path, legacy_user_id=None) — 全マイグレーションを順次実行

設計指針:
- 全マイグレーションは idempotent (二度実行してOK)
- 適用済みは `_migrations` テーブルで管理
- 破壊的変更前に `pill.db.bak.<unixtime>` を作成
- v1 既存データは `servings_v1` として保持 (rollback用)
"""
from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path


# ---------- 共通ヘルパ ----------

def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )


def _migration_applied(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM _migrations WHERE name=?", (name,)
    ).fetchone()
    return row is not None


def _record_migration(conn: sqlite3.Connection, name: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO _migrations (name) VALUES (?)", (name,)
    )


def _backup_db(db_path: Path) -> Path | None:
    """SQLiteファイルが既存・非空ならバックアップ。"""
    if db_path.exists() and db_path.stat().st_size > 0:
        backup = db_path.with_name(f"{db_path.name}.bak.{int(time.time())}")
        shutil.copy2(db_path, backup)
        return backup
    return None


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(r[1] == column for r in cur.fetchall())


def _is_v1_servings(conn: sqlite3.Connection) -> bool:
    """v1 形式 (servings あり、slot 列なし) かどうか。"""
    if not _table_exists(conn, "servings"):
        return False
    return not _has_column(conn, "servings", "slot")


# ---------- v2 スキーマ DDL ----------

V2_DDL_NON_SERVINGS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        line_user_id TEXT NOT NULL UNIQUE,
        display_name TEXT,
        contracted_clinic_id INTEGER,
        role TEXT NOT NULL DEFAULT 'user',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_users_clinic ON users(contracted_clinic_id)",
    """
    CREATE TABLE IF NOT EXISTS medications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('topical','oral','supplement','other')),
        is_preset INTEGER NOT NULL DEFAULT 0,
        created_by_user_id INTEGER,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
        UNIQUE(name, created_by_user_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_meds_preset ON medications(is_preset)",
    """
    CREATE TABLE IF NOT EXISTS user_medications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        medication_id INTEGER NOT NULL,
        slot TEXT NOT NULL CHECK(slot IN ('morning','evening')),
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (medication_id) REFERENCES medications(id) ON DELETE RESTRICT,
        UNIQUE(user_id, medication_id, slot)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_um_user_slot ON user_medications(user_id, slot, enabled)",
    """
    CREATE TABLE IF NOT EXISTS user_settings (
        user_id INTEGER PRIMARY KEY,
        morning_time TEXT NOT NULL DEFAULT '07:30',
        evening_time TEXT NOT NULL DEFAULT '22:00',
        evening_enabled INTEGER NOT NULL DEFAULT 1,
        timezone TEXT NOT NULL DEFAULT 'Asia/Tokyo',
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS serving_medications (
        serving_id INTEGER NOT NULL,
        medication_id INTEGER NOT NULL,
        PRIMARY KEY (serving_id, medication_id),
        FOREIGN KEY (serving_id) REFERENCES servings(id) ON DELETE CASCADE,
        FOREIGN KEY (medication_id) REFERENCES medications(id) ON DELETE RESTRICT
    )
    """,
]

V2_SERVINGS_DDL = [
    """
    CREATE TABLE IF NOT EXISTS servings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        scheduled_date TEXT NOT NULL,
        slot TEXT NOT NULL CHECK(slot IN ('morning','evening')),
        pushed_at TEXT,
        reminded_at TEXT,
        taken_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        UNIQUE(user_id, scheduled_date, slot)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_servings_user_date ON servings(user_id, scheduled_date)",
    "CREATE INDEX IF NOT EXISTS idx_servings_date ON servings(scheduled_date)",
]


def _create_v2_non_servings(conn: sqlite3.Connection) -> None:
    for stmt in V2_DDL_NON_SERVINGS:
        conn.execute(stmt)


def _create_v2_servings(conn: sqlite3.Connection) -> None:
    for stmt in V2_SERVINGS_DDL:
        conn.execute(stmt)


def _ensure_user_with_settings(
    conn: sqlite3.Connection, line_user_id: str
) -> int:
    """users 行と user_settings 行を idempotent に作成、users.id を返す。"""
    conn.execute(
        "INSERT OR IGNORE INTO users (line_user_id) VALUES (?)",
        (line_user_id,),
    )
    user_id = conn.execute(
        "SELECT id FROM users WHERE line_user_id=?", (line_user_id,)
    ).fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)",
        (user_id,),
    )
    return user_id


def _migrate_v1_servings_to_v2(
    conn: sqlite3.Connection, legacy_user_id: str | None
) -> None:
    """v1 servings → v2 servings 変換。

    手順:
    1. servings → servings_v1 にリネーム (rollback 用に保持)
    2. v2 servings を作成
    3. servings_v1 の distinct user_id を users に投入 (legacy_user_id 優先)
    4. v1行を v2 へコピー (slot='morning'、user_id を INTEGER FK にマッピング)
    """
    # 1) リネーム (idempotent: servings_v1 が既にあったらスキップ)
    if not _table_exists(conn, "servings_v1"):
        conn.execute("ALTER TABLE servings RENAME TO servings_v1")
    if _table_exists(conn, "servings"):
        # 既に v2 servings が存在 → 既マイグレ済 (この関数は呼ばれないはずだが防御)
        return

    # 2) v2 servings 作成
    _create_v2_servings(conn)

    # 3) ユーザー投入
    distinct_users = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT user_id FROM servings_v1"
        ).fetchall()
    ]
    if legacy_user_id and legacy_user_id not in distinct_users:
        distinct_users.append(legacy_user_id)
    for line_user_id in distinct_users:
        _ensure_user_with_settings(conn, line_user_id)

    # 4) コピー: line_user_id (TEXT) → users.id (INTEGER) にマッピング
    conn.execute(
        """
        INSERT INTO servings
            (user_id, scheduled_date, slot, pushed_at, reminded_at, taken_at)
        SELECT u.id, s.scheduled_date, 'morning', s.pushed_at, s.reminded_at, s.taken_at
          FROM servings_v1 s
          JOIN users u ON u.line_user_id = s.user_id
        """
    )


# ---------- 公開エントリ ----------

def run_001(db_path: Path, legacy_user_id: str | None = None) -> None:
    """Migration 001: v1 → v2 multi-user schema.

    Args:
        db_path: SQLiteファイルパス
        legacy_user_id: v1単一ユーザーのLINE user ID。
            v1 DBから移行するときに必須。新規DBなら None または任意の値。
    """
    _backup_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        _ensure_migrations_table(conn)
        if _migration_applied(conn, "001_multiuser"):
            return

        v1_present = _is_v1_servings(conn)

        with conn:  # transaction
            # v1 case: servings を先に rename してから v2 全テーブル作成
            if v1_present:
                _create_v2_non_servings(conn)
                _migrate_v1_servings_to_v2(conn, legacy_user_id)
            else:
                _create_v2_non_servings(conn)
                _create_v2_servings(conn)
                if legacy_user_id:
                    _ensure_user_with_settings(conn, legacy_user_id)

            _record_migration(conn, "001_multiuser")
    finally:
        conn.close()


# プリセット薬 (薬機法配慮: 一般名のみ)
PRESET_MEDICATIONS = [
    ("ミノキシジル外用", "topical"),
    ("ミノキシジル内服", "oral"),
    ("フィナステリド", "oral"),
    ("デュタステリド", "oral"),
    ("亜鉛", "supplement"),
    ("ビオチン", "supplement"),
]


def run_002(db_path: Path) -> None:
    """Migration 002: preset medications を投入。

    薬機法配慮: ブランド名 (フィンペシア / プロペシア / ザガーロ / ミノタブ等) は
    含めない。一般名のみ。
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        _ensure_migrations_table(conn)
        if _migration_applied(conn, "002_seed_meds"):
            return

        with conn:
            for name, kind in PRESET_MEDICATIONS:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO medications
                        (name, kind, is_preset, created_by_user_id)
                    VALUES (?, ?, 1, NULL)
                    """,
                    (name, kind),
                )
            _record_migration(conn, "002_seed_meds")
    finally:
        conn.close()


def run_003(db_path: Path) -> None:
    """Migration 003: user_settings にリマインダー設定カラムを追加。

    - reminder_mode: 'off' | 'interval' | 'fixed'
    - reminder_interval_hours: N時間おき（mode=interval のとき有効）
    - reminder_times: CSV 'HH:MM,HH:MM' 形式（mode=fixed のとき有効）
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        _ensure_migrations_table(conn)
        if _migration_applied(conn, "003_reminder_settings"):
            return

        with conn:
            if not _has_column(conn, "user_settings", "reminder_mode"):
                conn.execute(
                    "ALTER TABLE user_settings ADD COLUMN reminder_mode TEXT NOT NULL DEFAULT 'off'"
                )
            if not _has_column(conn, "user_settings", "reminder_interval_hours"):
                conn.execute(
                    "ALTER TABLE user_settings ADD COLUMN reminder_interval_hours INTEGER NOT NULL DEFAULT 0"
                )
            if not _has_column(conn, "user_settings", "reminder_times"):
                conn.execute(
                    "ALTER TABLE user_settings ADD COLUMN reminder_times TEXT NOT NULL DEFAULT ''"
                )
            _record_migration(conn, "003_reminder_settings")
    finally:
        conn.close()


def run_all(db_path: Path, legacy_user_id: str | None = None) -> None:
    """全マイグレーションを順次実行。idempotent。"""
    run_001(db_path, legacy_user_id=legacy_user_id)
    run_002(db_path)
    run_003(db_path)


if __name__ == "__main__":
    # CLI: python -m migrations.runner [legacy_user_id]
    import os
    import sys

    db_default = Path(__file__).parent.parent / "data" / "pill.db"
    legacy = os.environ.get("LEGACY_LINE_USER_ID") or (
        sys.argv[1] if len(sys.argv) > 1 else None
    )
    db_default.parent.mkdir(parents=True, exist_ok=True)
    run_all(db_default, legacy_user_id=legacy)
    print(f"[ok] migrations applied to {db_default}")
