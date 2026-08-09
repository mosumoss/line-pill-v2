"""1分ティック式 per-user push dispatcher。

launchd から1分ごとに起動される。全ユーザーの通知設定を確認し、
- 通常通知: morning_time / evening_time に一致したらプッシュ
- リマインダー: ユーザー設定 (interval / fixed) に従って飲み忘れリマインダー

設計原則:
- 冪等: pushed_at / reminded_at の原子的 UPDATE で重複送信を防ぐ
- IDOR安全: 各 serving の更新は user_id でスコープ
- テスト可能: push_fn を DI で差し替え可能
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from db import DB_PATH
from repositories.medications import list_user_medications
from repositories.servings import (
    Serving,
    get_or_create_serving,
    list_servings,
    set_pushed_at,
    set_reminded_at,
)
from repositories.users import UserSettings, get_settings


def _all_users(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    """全ユーザーの (id, line_user_id) を返す。"""
    rows = conn.execute("SELECT id, line_user_id FROM users ORDER BY id").fetchall()
    return [(r[0], r[1]) for r in rows]


def _hhmm_matches(now_local: datetime, target: str) -> bool:
    """now_local の HH:MM が target ('HH:MM') と一致するか。"""
    h, m = map(int, target.split(":"))
    return now_local.hour == h and now_local.minute == m


def _slots_to_push(now_local: datetime, settings: UserSettings) -> list[str]:
    """now_local においてプッシュすべきスロット名のリストを返す。"""
    slots = []
    if _hhmm_matches(now_local, settings.morning_time):
        slots.append("morning")
    if settings.evening_enabled and _hhmm_matches(now_local, settings.evening_time):
        slots.append("evening")
    return slots


def _parse_db_time(s: str | None) -> datetime | None:
    """SQLite datetime('now') 文字列 (UTC, naive) を aware UTC datetime に変換。"""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace(" ", "T")).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _should_remind(
    serving: Serving,
    settings: UserSettings,
    now_local: datetime,
    now_utc: datetime,
) -> bool:
    """今この瞬間にこの serving のリマインダーを送るべきか判定する。

    送る条件:
    - taken_at が NULL (未服用)
    - pushed_at が NOT NULL (1回は通常通知が送られた = リマインダーの起点となる時刻が決まっている)
    - reminder_mode が 'interval' or 'fixed'
    - interval: 直近の通知 (pushed_at or reminded_at) から interval_hours 経過
    - fixed:    reminder_times のいずれかに HH:MM が一致 + 当日まだリマインダー未送信
    """
    if serving.taken_at is not None:
        return False
    if serving.pushed_at is None:
        return False

    mode = settings.reminder_mode
    if mode == "off":
        return False

    if mode == "interval":
        hours = settings.reminder_interval_hours
        if hours <= 0:
            return False
        last_notified = _parse_db_time(serving.reminded_at) or _parse_db_time(serving.pushed_at)
        if last_notified is None:
            return False
        elapsed = now_utc - last_notified
        # 1分ティックなので tolerance 30 秒で「N時間経過」と判定
        return elapsed >= timedelta(hours=hours) - timedelta(seconds=30)

    if mode == "fixed":
        times_csv = settings.reminder_times.strip()
        if not times_csv:
            return False
        targets = [t.strip() for t in times_csv.split(",") if t.strip()]
        # 現在の HH:MM がいずれかに一致するか
        if not any(_hhmm_matches(now_local, t) for t in targets):
            return False
        # 当日既にリマインドしていれば二重送信しない (interval 衝突対策)
        reminded_at = _parse_db_time(serving.reminded_at)
        if reminded_at is not None:
            reminded_local = reminded_at.astimezone(now_local.tzinfo)
            if reminded_local.date() == now_local.date():
                # 既に当日リマインド済 → 同じ HH:MM の二度打ちを防ぐ
                if _hhmm_matches(reminded_local, reminded_local.strftime("%H:%M")):
                    return False
        return True

    return False


def run_tick(
    db_path: Path | None = None,
    now: datetime | None = None,
    *,
    push_fn: Callable[..., None] | None = None,
) -> list[str]:
    """1分ティック処理。通常通知 + リマインダーを送信する。

    Returns:
        通知 (通常 or リマインダー) を送信した line_user_id のリスト (重複あり)。
    """
    if push_fn is None:
        from line_api import push_reminder
        push_fn = push_reminder

    if db_path is None:
        db_path = DB_PATH

    if now is None:
        now = datetime.now(tz=timezone.utc)

    notified: list[str] = []

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        for user_id, line_user_id in _all_users(conn):
            settings = get_settings(conn, user_id)
            if settings is None:
                continue

            try:
                tz = ZoneInfo(settings.timezone)
            except ZoneInfoNotFoundError:
                continue

            now_local = now.astimezone(tz)
            today_str = now_local.date().isoformat()

            # ---- 1. 通常通知 (morning_time / evening_time) ----
            for slot in _slots_to_push(now_local, settings):
                if not list_user_medications(conn, user_id=user_id, slot=slot):
                    continue

                serving = get_or_create_serving(
                    conn, user_id=user_id, date=today_str, slot=slot
                )
                if not set_pushed_at(conn, serving_id=serving.id, user_id=user_id):
                    continue  # 既にプッシュ済み → スキップ

                push_fn(line_user_id, slot, serving.id)
                notified.append(line_user_id)

            # ---- 2. リマインダー (今日の未服用 servings) ----
            if settings.reminder_mode == "off":
                continue

            todays_servings = list_servings(
                conn, user_id=user_id, from_date=today_str, to_date=today_str
            )
            for serving in todays_servings:
                if not _should_remind(serving, settings, now_local, now):
                    continue
                if not set_reminded_at(conn, serving_id=serving.id, user_id=user_id):
                    continue  # 既に taken_at が入った → 服用済み
                push_fn(line_user_id, serving.slot, serving.id, is_followup=True)
                notified.append(line_user_id)
    finally:
        conn.close()

    return notified


if __name__ == "__main__":
    notified = run_tick()
    print(f"[tick] notified {len(notified)} push(es): {notified}")
