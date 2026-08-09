"""migration 002 (preset medications seeding) のテスト。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from migrations.runner import run_001, run_002


# 6 generic-name presets (薬機法配慮: ブランド名は含めない)
EXPECTED_PRESETS = [
    ("ミノキシジル外用", "topical"),
    ("ミノキシジル内服", "oral"),
    ("フィナステリド", "oral"),
    ("デュタステリド", "oral"),
    ("亜鉛", "supplement"),
    ("ビオチン", "supplement"),
]


class TestSeedPresets:
    def test_inserts_six_presets(self, empty_db: Path) -> None:
        run_001(empty_db)
        run_002(empty_db)
        conn = sqlite3.connect(empty_db)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM medications WHERE is_preset=1"
            ).fetchone()[0]
            assert count == 6
        finally:
            conn.close()

    def test_presets_have_correct_names_and_kinds(self, empty_db: Path) -> None:
        run_001(empty_db)
        run_002(empty_db)
        conn = sqlite3.connect(empty_db)
        try:
            rows = conn.execute(
                "SELECT name, kind FROM medications WHERE is_preset=1 ORDER BY id"
            ).fetchall()
            assert rows == EXPECTED_PRESETS
        finally:
            conn.close()

    def test_no_brand_names_in_presets(self, empty_db: Path) -> None:
        """薬機法配慮: ブランド名 (フィンペシア/プロペシア/ザガーロ/ミノタブ等) を含まないこと。"""
        run_001(empty_db)
        run_002(empty_db)
        forbidden_brands = ["フィンペシア", "プロペシア", "ザガーロ", "ミノタブ", "フィナロイド"]
        conn = sqlite3.connect(empty_db)
        try:
            names = [
                r[0]
                for r in conn.execute("SELECT name FROM medications").fetchall()
            ]
            for brand in forbidden_brands:
                assert brand not in names, f"未承認ブランド名 {brand} がプリセットに含まれる"
        finally:
            conn.close()


class TestSeedIdempotency:
    def test_run_twice_no_duplicates(self, empty_db: Path) -> None:
        run_001(empty_db)
        run_002(empty_db)
        run_002(empty_db)
        conn = sqlite3.connect(empty_db)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM medications WHERE is_preset=1"
            ).fetchone()[0]
            assert count == 6
        finally:
            conn.close()

    def test_recorded_in_migrations_table(self, empty_db: Path) -> None:
        run_001(empty_db)
        run_002(empty_db)
        conn = sqlite3.connect(empty_db)
        try:
            row = conn.execute(
                "SELECT name FROM _migrations WHERE name='002_seed_meds'"
            ).fetchone()
            assert row is not None
        finally:
            conn.close()
