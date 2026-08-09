# line-pill v2

LIFF版 育毛特化 服薬リマインダー (multi-user, LINE-completed UX)。

## v1 → v2 主な変更

| 項目 | v1 | v2 |
|---|---|---|
| ユーザー | 1人 (`.env` の `LINE_USER_ID`) | マルチユーザー |
| UI | Flex Message のみ | Rich Menu + LIFF (Calendar/Settings/Stats) |
| 通知時刻 | 7:30 / 22:00 固定 | ユーザーごと設定可 |
| 薬の管理 | コード内ハードコード (ミノキシジル + フィンペシア) | プリセット + ユーザー追加、朝晩別設定 |
| Static hosting | なし | Cloudflare Pages (LIFF SPA) |
| Tunnel | quick (URL変動) | named (URL固定) |
| Python | 3.9.6 | 3.11+ |

詳細設計: `../2026-05-06-line-pill-v2-design/`

## ディレクトリ構成

```
line-pill-v2-source/
├── migrations/         # DDL マイグレーション (001_multiuser.py, 002_seed_meds.py)
├── repositories/       # データアクセス (users.py, medications.py, servings.py)
├── routers/            # FastAPI ルーター (api.py, webhook.py)
├── scripts/            # 運用スクリプト (setup_rich_menu.py)
├── tests/              # pytest スイート (TDD ファーストで作成)
├── data/               # pill.db (gitignore)
├── docs/               # 開発メモ
├── auth.py             # LIFF ID token 検証 (LINE JWKs)
├── push_runner.py      # 1分ティック式 push dispatcher
├── line_api.py         # LINE Messaging API クライアント (v1から拡張)
├── server.py           # FastAPI エントリ
├── requirements.txt    # 本番依存
├── requirements-dev.txt # テスト・開発依存
├── pyproject.toml      # pytest 設定
├── .env.example        # 環境変数テンプレート
└── .gitignore
```

## セットアップ (開発環境)

```bash
cd line-pill-v2-source
python3.11 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env  # 値を埋める
./venv/bin/pytest -v
```

## TDD 開発ルール

各 Phase で以下のサイクル:
1. **RED**: 失敗するテストを書く
2. **GREEN**: 最小実装でテストを通す
3. **REFACTOR**: 重複・命名・構造を改善
4. カバレッジ 80% 以上を確認

## Phase 進捗

- [x] **A0**: プロジェクト構造 + dev tooling
- [x] **A1**: DB migration 001 + 002 (TDD) — 20 tests pass, coverage 94%
- [x] **A2**: users repository (TDD) — 26 tests, 100% coverage
- [x] **A3**: medications repository (TDD) — 23 tests, 100% coverage
- [x] **A4**: servings refactor with slot (TDD) — 22 tests, 100% coverage
- [x] **A5**: Auth middleware - LIFF ID token (TDD) — 11 tests, 100% coverage
- [x] **A6**: REST API endpoints (TDD) — 24 tests, 95% coverage
- [x] **A7**: Per-user push dispatcher (TDD) — 11 tests, 85% coverage
- **合計: 137 tests pass, coverage 92.21%**
- [x] **B**: LIFF foundation — SvelteKit + Svelte 5 runes + adapter-static, 15 tests pass, `npm run build` 成功
- [x] **C**: Calendar screen — calendar-utils 19 tests, 月グリッド + 日タップドロワー
- [x] **D**: Settings screen — settings-utils 6 tests (isValidHHMM / sanitizeSettings)
- [x] **E**: Stats screen — stats-utils 11 tests (adherenceRate / currentStreak / takenCount)
- **フロントエンド合計: 51 tests pass, `npm run build` ✓**
- [x] **F**: Rich Menu — `scripts/setup_rich_menu.py`
- [ ] **G**: Migration & cutover → `docs/phase-g-migration.md` 参照
