"""FastAPI DB dependency — リクエストごとに SQLite 接続を提供する。"""
from __future__ import annotations

import os
import sqlite3
from collections.abc import Generator
from pathlib import Path

DB_PATH: Path = Path(os.environ.get("PILL_DB_PATH", "data/pill.db"))


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI Depends 用。リクエスト開始時に接続を確立し、終了時にクローズ。

    check_same_thread=False: FastAPI の async ランタイムが finally ブロック (close)
    を別スレッドで実行することがあるため。リクエストごとに新規接続を作るので
    接続自体は共有されず、スレッド境界を越えるのは close 操作のみで安全。
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()
