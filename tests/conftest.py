"""共通 pytest fixtures。"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

# プロジェクトルートを sys.path に追加 (migrations/, repositories/ をimport可能に)
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def empty_db(tmp_path: Path) -> Path:
    """ファイルシステム上に空のSQLiteファイルだけ作成。"""
    db_path = tmp_path / "test_empty.db"
    conn = sqlite3.connect(db_path)
    conn.close()
    return db_path


@pytest.fixture
def v1_db(tmp_path: Path) -> Path:
    """v1 スキーマ + シードデータの SQLite。

    v1 では single user の前提で `servings` 1テーブル。
    マイグレーションテストの入力として使う。
    """
    db_path = tmp_path / "test_v1.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE servings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            scheduled_date TEXT NOT NULL,
            pushed_at TEXT,
            reminded_at TEXT,
            taken_at TEXT,
            UNIQUE(user_id, scheduled_date)
        );
        CREATE INDEX idx_servings_date ON servings(scheduled_date);
        CREATE INDEX idx_servings_user ON servings(user_id);
        """
    )
    conn.executemany(
        """INSERT INTO servings (user_id, scheduled_date, pushed_at, taken_at)
           VALUES (?, ?, ?, ?)""",
        [
            # 飲んだ
            ("U_TEST_USER_001", "2026-04-30", "2026-04-30T07:30:00", "2026-04-30T08:15:00"),
            # 飲んだ
            ("U_TEST_USER_001", "2026-05-01", "2026-05-01T07:30:00", "2026-05-01T08:00:00"),
            # 飲み忘れ (taken_at NULL)
            ("U_TEST_USER_001", "2026-05-02", "2026-05-02T07:30:00", None),
        ],
    )
    conn.commit()
    conn.close()
    return db_path


def table_names(db_path: Path) -> set[str]:
    """SQLiteファイル内のテーブル名集合を返す。"""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        return {r[0] for r in cur.fetchall()}
    finally:
        conn.close()


def column_names(db_path: Path, table: str) -> set[str]:
    """指定テーブルのカラム名集合を返す。"""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(f"PRAGMA table_info({table})")
        return {r[1] for r in cur.fetchall()}
    finally:
        conn.close()
