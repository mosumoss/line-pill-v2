# Phase G: èªå®ãµã¼ãã¼ 移行・カットオーバー手順書

v1 (èªå®ãµã¼ãã¼ 稼働中) → v2 (èªå®ãµã¼ãã¼ 上で並走 → 切り替え) の手順。

---

## 前提確認

| 項目 | 内容 |
|---|---|
| èªå®ãµã¼ãã¼ 上の v1 | `~/line-pill/` など既存ディレクトリ |
| v1 DB パス | `~/line-pill/data/pill.db` (実際のパスを確認) |
| v1 の LINE_USER_ID | `.env` の `LINE_USER_ID` を控える |
| Python バージョン | v2 は **3.11+** が必要 (`python3 --version` 確認) |
| Cloudflare アカウント | LIFF SPA のデプロイ先 (Pages) |
| LINE Developers | LIFF アプリ登録・Rich Menu 設定 |

---

## G-0: 事前作業 (èªå®ãµã¼ãã¼ にSSH接続する前に完了させる)

### G-0-1: LINE Developers でLIFF アプリ登録

> **重要**: LIFFは Messaging API チャネルには追加不可（2019年以降）。
> **LINE Login チャネル** に登録する。Messaging API チャネルと**同じプロバイダー**配下に置くこと。

1. [LINE Developers コンソール](https://developers.line.biz/console/) を開く
2. 既存の Messaging API チャネルと**同じプロバイダー**を選択
3. **「チャネル作成」→「LINE ログイン」** で新規チャネルを作成
   - チャネル名: `line-pill-v2`
   - アプリタイプ: **ウェブアプリ**
4. 作成した LINE Login チャネルの **「LIFF」タブ → 「追加」**
5. 設定値:

   | 項目 | 値 |
   |---|---|
   | 名前 | line-pill-v2 |
   | サイズ | **Full** |
   | エンドポイントURL | `https://pill.pages.dev` (後で変更可) |
   | Scope | `profile openid` |
   | Bot連携 | **On (Aggressive)** |

6. 発行された **LIFF ID** (例: `1234567890-AbCdEfGh`) を控える
7. **LINE Login チャネルの「チャネル基本設定」→「チャネルID」** (数字のみ) も控える
   - これが `LIFF_CHANNEL_ID` 環境変数の値になる（Messaging API のチャネルIDではない）

### G-0-2: Cloudflare Pages プロジェクト作成

> **前提**: èªå®ãµã¼ãã¼ のトンネル URL (G-5 完了後) が確定してから実施すること。
> LIFF ID だけ先に取得しておき、`.env.production.local` は G-5 後に完成させる。

```bash
# ローカル MacBook で実行
cd line-pill-v2-source/liff

# .env.production.local に値を埋める (LIFF ID は G-0-1 で確定済み)
# VITE_API_BASE は G-5 のトンネル URL 確定後に更新
VITE_LIFF_ID=2009984865-HCm8IfvR
VITE_API_BASE=https://<èªå®ãµã¼ãã¼ のトンネル URL>/api   # ← G-5 後に確定
VITE_LIFF_MOCK=false

npm run build

# Cloudflare にデプロイ
npx wrangler pages deploy build --project-name line-pill-v2
```

デプロイ後に発行される `*.pages.dev` URL を LINE Developers のエンドポイントURLに設定する。

### G-0-3: èªå®ãµã¼ãã¼ のポート開放確認

v2 は **8001** 番ポートで起動する想定 (v1 が 8000 を使用中の場合)。

```bash
# èªå®ãµã¼ãã¼ で確認
sudo lsof -i :8000   # v1 が使っているポート
sudo lsof -i :8001   # v2 用 (空いているか確認)
```

---

## G-1: èªå®ãµã¼ãã¼ にv2コードを配置

```bash
# èªå®ãµã¼ãã¼ にSSH接続
ssh apple@<<server-alias>-ip>

# v2 ソースを配置 (ローカルからscp or git clone)
cd ~
# 方法A: ローカルからscpで転送
#   (MacBook側で実行)
#   scp -r "<project-root>" apple@<<server-alias>-ip>:~/line-pill-v2

# 方法B: Gitリポジトリがあれば clone

# 配置確認
ls ~/line-pill-v2/
```

---

## G-2: Python 環境セットアップ

```bash
cd ~/line-pill-v2

# Python 3.11 確認 (なければ Homebrew でインストール)
python3.11 --version
# brew install python@3.11

# venv 作成
python3.11 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# テスト用依存も入れて確認
./venv/bin/pip install -r requirements-dev.txt
./venv/bin/pytest tests/ -q
# → 137 passed が出ることを確認
```

---

## G-3: 環境変数ファイル (.env) 作成

```bash
cd ~/line-pill-v2
cp .env.example .env
nano .env  # 以下を設定
```

```dotenv
# LINE
LIFF_CHANNEL_ID=<LINE Login チャネルのチャネルID ※Messaging APIのIDではない>
LINE_CHANNEL_ACCESS_TOKEN=<Messaging API チャネルアクセストークン>

# DB (v2 専用の新しいパス)
DB_PATH=<project-root>/data/pill.db

# サーバー
HOST=0.0.0.0
PORT=8001
```

```bash
# data ディレクトリ作成
mkdir -p data
```

---

## G-4: DB マイグレーション実行

### 新規 DB の場合 (v1 データを引き継がない)

```bash
cd ~/line-pill-v2
./venv/bin/python -m migrations.runner
# → [ok] migrations applied to data/pill.db
```

### v1 DB からデータ移行する場合

```bash
# v1 の LINE_USER_ID を環境変数にセット
export LEGACY_LINE_USER_ID=Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# v1 DB をコピー (移行元。絶対に v1 の本番 DB を直接渡さない)
cp ~/line-pill/data/pill.db ~/line-pill-v2/data/pill.db

# マイグレーション実行 (v1 servings → v2 スキーマに変換)
./venv/bin/python -m migrations.runner "$LEGACY_LINE_USER_ID"
```

**マイグレーションが行うこと:**
- `pill.db.bak.<unixtime>` にバックアップを自動作成 (ロールバック用)
- `servings` → `servings_v1` にリネーム保持 (削除しない)
- v2 スキーマ (users / user_settings / medications 等) を作成
- v1 の服薬履歴を v2 `servings` に `slot='morning'` として移行

---

## G-5: v2 サーバーを並走起動

```bash
cd ~/line-pill-v2

# バックグラウンドで起動 (v1 は 8000 のまま継続稼働)
nohup ./venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001 > logs/uvicorn.log 2>&1 &
echo $! > logs/uvicorn.pid

# ヘルスチェック
curl -s http://localhost:8001/health | python3 -m json.tool
```

---

## G-6: push_runner を cron に登録

```bash
# crontab 編集
crontab -e
```

以下を追加 (v1 の cron 行は **まだ残す**):

```cron
# line-pill v2 push runner (1分ごと)
* * * * * cd <project-root> && ./venv/bin/python push_runner.py >> logs/push.log 2>&1
```

```bash
# logs ディレクトリ作成
mkdir -p ~/line-pill-v2/logs
```

---

## G-7: 動作確認 (並走フェーズ)

v2 サーバーと v1 を**同時に**動かして動作を確認する。

```bash
# v2 の API が返答するか (LINE ID token なしで 401 が返れば正常)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/me
# → 401 または 403

# DB に users テーブルが存在するか
sqlite3 ~/line-pill-v2/data/pill.db ".tables"

# push_runner のログを確認
tail -f ~/line-pill-v2/logs/push.log
```

**LIFF 動作確認 (スマホで):**
1. LINE アプリ → チャット画面で `https://liff.line.me/<LIFF ID>` を開く
2. 今日の服薬画面が表示されるか確認
3. 服薬ボタンをタップ → チェックが付くか確認
4. カレンダー / 設定 / 統計 が開くか確認

---

## G-8: Rich Menu セットアップ

```bash
cd ~/line-pill-v2

# scripts/rich_menu.png を配置 (2500×843px, PNG, ≤1MB)
# ← 画像を事前に作成しておく (Canva や Figma で作成可能)
ls scripts/rich_menu.png

# セットアップスクリプト実行
LIFF_ID=<LIFF ID> \
LINE_CHANNEL_ACCESS_TOKEN=<トークン> \
./venv/bin/python scripts/setup_rich_menu.py
```

**Rich Menu レイアウト:**

```
┌────────────┬────────────┬────────────┐
│            │            │            │
│  今日の服薬  │ カレンダー  │    設定    │
│    (左)    │   (中)     │   (右)    │
└────────────┴────────────┴────────────┘
```

---

## G-9: カットオーバー (v1 → v2 切り替え)

並走フェーズで問題がなければ切り替える。

### G-9-1: v1 の cron を停止

```bash
crontab -e
# v1 の push runner 行をコメントアウト
# # * * * * * ... line-pill v1 ...
```

### G-9-2: v1 の uvicorn を停止

```bash
# v1 の PID を確認して停止
kill $(cat ~/line-pill/logs/uvicorn.pid 2>/dev/null) 2>/dev/null || \
  pkill -f "uvicorn.*8000"
```

### G-9-3: Cloudflare Pages のエンドポイントを確認

`VITE_API_BASE` が èªå®ãµã¼ãã¼ の正しいアドレスを向いているか再確認。

```bash
# ローカル MacBook で
cd line-pill-v2-source/liff
cat .env.production.local
# VITE_API_BASE=https://pill-api.example.com/api  ← ngrok named tunnel or reverse proxy
```

### G-9-4: LINE Developers で LIFF エンドポイントを本番 URL に更新

コンソールで LIFF アプリのエンドポイントを `*.pages.dev` の本番 URL に設定。

---

## G-10: カットオーバー後の確認チェックリスト

```
[ ] curl http://localhost:8001/health → {"status": "ok"}
[ ] LIFF 今日の服薬画面が開く
[ ] 服薬ボタンが動作する (DB に反映される)
[ ] push_runner.log に ERROR がない
[ ] Rich Menu が LINE チャット画面に表示される
[ ] v1 の push が止まっている (二重通知なし)
[ ] DB バックアップが存在する: ls ~/line-pill-v2/data/pill.db.bak.*
```

---

## ロールバック手順

問題が発生した場合:

```bash
# v2 を停止
kill $(cat ~/line-pill-v2/logs/uvicorn.pid)
crontab -e  # v2 cron をコメントアウト

# v1 を再起動
cd ~/line-pill
nohup ./venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000 > logs/uvicorn.log 2>&1 &
crontab -e  # v1 cron のコメントアウトを解除

# v2 DB を migrated 前に戻す場合
ls ~/line-pill-v2/data/pill.db.bak.*
cp ~/line-pill-v2/data/pill.db.bak.<unixtime> ~/line-pill-v2/data/pill.db
```

---

## ngrok Named Tunnel (オプション)

èªå®ãµã¼ãã¼ に固定ドメインを割り当てるために ngrok named tunnel を使う場合。

```bash
# èªå®ãµã¼ãã¼ で
ngrok config add-authtoken <your-token>

# ngrok.yml に named tunnel 設定
cat ~/.config/ngrok/ngrok.yml
```

```yaml
version: "3"
agent:
  authtoken: <your-token>
tunnels:
  pill-api:
    proto: http
    addr: 8001
    hostname: pill-api.your-ngrok-domain.app
```

```bash
# 起動
ngrok start pill-api &

# macOS 自動起動 (launchd)
# ~/.config/ngrok/com.ngrok.pill-api.plist を作成して launchctl load
```

---

## 更新履歴
- 2026-05-06: 初版作成。Phase G 全ステップを文書化。
