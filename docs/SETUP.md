# LINE 服薬リマインダー — セットアップ記録

èªå®ãµã¼ãã¼（24時間稼働の自宅サーバー）上に、LINE 経由で毎朝7:30に「ミノキシジル + フィンペシアを服用してください」と通知し、ボタン押下で服用記録を残す仕組みを構築する。未押下時は22:00に1回リマインド（合計2回）。

将来的に商用化（マルチユーザー化、薬機法準拠）も視野に入れる。Phase 1 は自分用 MVP。

---

## 現状

| 項目 | 状態 |
|---|---|
| èªå®ãµã¼ãã¼ SSH 疎通 | OK（`ssh <server-alias>`、鍵認証済み） |
| èªå®ãµã¼ãã¼ ホーム | `~` |
| èªå®ãµã¼ãã¼ アーキテクチャ | arm64（Apple Silicon） |
| èªå®ãµã¼ãã¼ macOS | 26.4.1 |
| Python 3 | `/usr/bin/python3` 存在するが Xcode CLT 未インストールで起動不可 |
| Homebrew | 未インストール |
| cloudflared | 未インストール |
| ポート 3000 | 空き |
| LINE 公式アカウント | 作成済み（Token 等保有） |
| Cloudflare アカウント・ドメイン | 両方なし → quick tunnel で対応 |

---

## システム構成図

```
[7:30] launchd ──┐
                 ├──→ push_morning.py ──→ LINE Messaging API ──→ あなたのLINE
[22:00] launchd ─┘                                                「服用してください」
                 └──→ push_evening.py                              [✅ 服用した]
                      (今日未押下時のみ送信)                            │
                                                                       ▼
                                                              LINE Platform
                                                                       │ webhook (postback)
                                                                       ▼
                                                       ┌─ Cloudflare Tunnel (quick) ─┐
                                                       └────── HTTPS 永続接続 ────────┘
                                                                       │
                                                                       ▼
                                                            server.py (FastAPI / port 3000)
                                                            - 署名検証
                                                            - SQLite に taken_at 記録
                                                            - 「✅ 記録しました」reply
```

---

## 利用技術と役割（初心者向け解説）

### インフラ層（èªå®ãµã¼ãã¼ にインストールするもの）

| ツール | 一行説明 | 今回の役割 |
|---|---|---|
| **Xcode Command Line Tools** | Apple公式の開発基礎セット（コンパイラ、git、python補助） | macOS の `python3` を動かすための前提 |
| **Homebrew** | macOS 用パッケージマネージャ（App Store のターミナル版） | `cloudflared` を簡単インストール |
| **cloudflared** | Cloudflare 製トンネルクライアント | 家のLAN内 èªå®ãµã¼ãã¼ に LINEサーバから HTTPS で到達するための「内→外」トンネル |
| **launchd** | macOS 純正のジョブスケジューラ（Linux の cron + systemd 相当） | 7:30 / 22:00 の定時実行 + サーバ常駐化 + èªå®ãµã¼ãã¼ 再起動後の自動復帰 |

### アプリ層（Python で書く）

| ツール | 一行説明 | 今回の役割 |
|---|---|---|
| **venv** | Python 仮想環境。プロジェクト単位で依存ライブラリを隔離 | システム Python を汚さない |
| **FastAPI** | 軽量 Web フレームワーク。型ヒント前提で書きやすい | Webhook サーバ本体 |
| **uvicorn** | ASGI サーバ。FastAPI を実際に動かす実行エンジン | webhook を port 3000 で待ち受け |
| **httpx** | 現代的な Python HTTP クライアント | LINE API への push 送信 |
| **SQLite** | ファイル1個で完結する組込み DB | `data/pill.db` に服用記録 |

### 外部サービス

| サービス | 一行説明 | 今回の役割 |
|---|---|---|
| **LINE Messaging API** | LINE 公式アカウント用の開発者向け API | push 送信、Webhook 受信、reply |
| **Postback Action** | 「文字を出さず裏でサーバにイベント送信」できる LINE のボタン仕様 | 「✅ 服用した」ボタンの実装方法 |
| **Cloudflare Tunnel (quick mode)** | アカウント不要で `https://xxx.trycloudflare.com` を発行する無料トンネル | Webhook URL の公開（プロセス再起動で URL は変動） |

---

## cloudflared の仕組み（重要なので詳細）

```
LINEサーバ → https://xxx.trycloudflare.com → Cloudflareの基地
                                                  ↓
                                   暗号化された永続接続（cloudflaredが「内→外」に張る）
                                                  ↓
                                              èªå®ãµã¼ãã¼（家のLAN内）
                                                  ↓
                                            server.py (port 3000)
```

- **接続方向は内→外**: ルーターのポート開放不要
- **HTTPS は自動付与**: 自前で SSL 証明書を取らなくていい
- **無料**: Cloudflare アカウントすら不要（quick tunnel の場合）
- **ハマる可能性**: プロセス再起動で URL 変動 → launchd で常駐化することで èªå®ãµã¼ãã¼ 再起動時のみに限定

---

## 手順

### ステップ1: èªå®ãµã¼ãã¼ で前提セットアップ（人手作業）

èªå®ãµã¼ãã¼ に直接ログインして実行（sudo パスワード入力必要）:

```bash
# 1. Xcode CLT（GUIダイアログ → Installクリック）
xcode-select --install

# 2. Homebrew（途中で sudo パスワード入力）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 3. PATH を通す（Apple Silicon）
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"

# 4. cloudflared
brew install cloudflared

# 5. 確認
brew --version && cloudflared --version && python3 --version
```

### ステップ2: プロジェクト構築（Claude が SSH 経由で実施）

```
~/line-pill/
├── .env                 ← Token類（あなたが SSH 経由で記入）
├── requirements.txt
├── server.py            ← FastAPI webhook（常駐）
├── push_morning.py      ← 朝7:30
├── push_evening.py      ← 22:00条件付き
├── db_init.py
├── data/pill.db         ← SQLite
└── README.md
```

### ステップ3: LINE Developers Console で Webhook URL 登録（人手作業）

cloudflared 起動後に表示される `https://xxx.trycloudflare.com/callback` を LINE Developers Console の Messaging API 設定に登録。

### ステップ4: launchd 登録（Claude が実施）

```
~/Library/LaunchAgents/
├── com.morimoto.line-pill.server.plist    ← uvicorn 常駐
├── com.morimoto.line-pill.tunnel.plist    ← cloudflared 常駐
├── com.morimoto.line-pill.morning.plist   ← 7:30
└── com.morimoto.line-pill.evening.plist   ← 22:00
```

### ステップ5: 動作確認

1. `curl` で webhook 疎通テスト
2. `python push_morning.py` 手動実行 → LINE に到達確認
3. ボタン押下 → 完了 reply 確認
4. SQLite に `taken_at` が記録されているか確認
5. 翌朝7:30の自動送信を待つ

---

## トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `python3` 実行で「No developer tools found」ダイアログ | Xcode CLT 未インストール | `xcode-select --install` |
| `brew: command not found` | PATH 未設定 | `eval "$(/opt/homebrew/bin/brew shellenv)"` |
| LINE webhook が 401 を返す | 署名検証失敗 / Channel Secret ミス | `.env` の `LINE_CHANNEL_SECRET` 確認 |
| èªå®ãµã¼ãã¼ 再起動後 webhook が到達しない | cloudflared の URL が変わった | 「cloudflared URL 更新手順」セクション参照 |
| 7:30 に push が来ない | launchd 未登録 / システムスリープ | `launchctl list \| grep line-pill`、`pmset -g` で sleep 確認 |
| push が 401 / Token無効エラー | Channel Access Token 失効・再発行後の未更新 | 「Token 再発行手順」セクション参照 |
| サーバが起動直後にクラッシュ | `.env` 必須項目欠落（F2 起動時バリデーション） | `~/logs/line-pill/server.stderr.log` 末尾を確認、足りない env を `.env` に追記してサーバ再起動 |
| ボタン2回押しで毎回「記録しました」が出る | F3 修正前の古い db.py | `~/line-pill/db.py` が `INSERT...ON CONFLICT DO UPDATE WHERE taken_at IS NULL` を含むか確認 |

---

## 運用チートシート

### launchd 日常操作

```bash
# 全サービスの状態確認（PID列が数字なら稼働中、- なら待機中）
launchctl list | grep line-pill

# サービス手動再起動（最も使う）
launchctl kickstart -k gui/$(id -u)/com.morimoto.line-pill.server
launchctl kickstart -k gui/$(id -u)/com.morimoto.line-pill.tunnel

# 手動でジョブを今すぐ実行（cron時刻を待たずに）
launchctl kickstart gui/$(id -u)/com.morimoto.line-pill.morning
launchctl kickstart gui/$(id -u)/com.morimoto.line-pill.evening

# サービス完全停止
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.morimoto.line-pill.server.plist

# サービス再登録（plist 編集後など）
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.morimoto.line-pill.server.plist

# ログ追跡（リアルタイム）
tail -f ~/logs/line-pill/server.log         # webhook 受信履歴
tail -f ~/logs/line-pill/push_morning.log   # 朝 push 履歴
tail -f ~/logs/line-pill/push_evening.log   # 夜 push 履歴
tail -f ~/logs/line-pill/cloudflared.stdout.log  # トンネルURL含む
```

### cloudflared URL 更新手順（èªå®ãµã¼ãã¼ 再起動後など）

quick tunnel は cloudflared プロセスが再起動するたびに新URLを発行する。èªå®ãµã¼ãã¼ の電源OFF/再起動後は以下を必ず実行。

```bash
# 1. cloudflared が起動しているか確認
launchctl list | grep line-pill.tunnel

# 2. 現在の URL をログから取得
grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' \
    ~/logs/line-pill/cloudflared.stdout.log \
    ~/logs/line-pill/cloudflared.stderr.log 2>/dev/null | tail -1
```

3. ブラウザで LINE Developers Console (https://developers.line.biz/console/) にアクセス
4. 対象チャネル → 「Messaging API」タブ → 「Webhook URL」→ 「Edit」
5. 取得した URL に `/callback` を付けて貼り付け（例: `https://xxx-yyy-zzz.trycloudflare.com/callback`）→ Update
6. 「Verify」ボタン → Success が出れば完了

### Token 再発行手順（Token 漏洩時 / 定期ローテーション）

1. LINE Developers Console → 対象チャネル → 「Messaging API」タブ
2. 「Channel access token」セクション → 「Reissue」（Issue ボタンが Reissue になっている）
3. 新しいトークンをコピー
4. èªå®ãµã¼ãã¼ で `.env` 更新:

```bash
# 既存値を確認（値は表示しない）
awk -F= 'NF>=2 { print $1 ": [SET, " length($2) "chars]" }' ~/line-pill/.env

# nano で編集
nano ~/line-pill/.env
# LINE_CHANNEL_ACCESS_TOKEN= の右側を新トークンに置き換え → Ctrl+O / Enter / Ctrl+X
```

5. サーバ再起動して新トークン反映:

```bash
launchctl kickstart -k gui/$(id -u)/com.morimoto.line-pill.server
```

6. push 動作確認:

```bash
~/line-pill/venv/bin/python ~/line-pill/push_morning.py
# → "morning push OK" が出れば成功
```

### Channel Secret 再発行時も同様

Channel Secret を Reissue した場合は `.env` の `LINE_CHANNEL_SECRET` を書き換え + サーバ再起動。webhook 署名検証は新Secretで動く。

---

## チェックリスト

### 前提セットアップ（èªå®ãµã¼ãã¼ 側、人手作業）
- [x] Xcode Command Line Tools インストール完了
- [x] Homebrew インストール完了 + PATH 設定
- [x] cloudflared インストール完了
- [x] `brew --version` / `cloudflared --version` / `python3 --version` 全て応答

### プロジェクト構築
- [x] `~/line-pill/` ディレクトリ作成
- [x] venv + 依存インストール
- [x] `.env` テンプレート作成
- [x] `db_init.py` 実装 + `pill.db` 初期化
- [x] `server.py` 実装（FastAPI + 署名検証 + postback 処理）
- [x] `push_morning.py` 実装
- [x] `push_evening.py` 実装（条件付き送信）

### Token 設定（人手作業）
- [x] LINE Channel Access Token 取得・記入
- [x] LINE Channel Secret 取得・記入
- [x] 自分の LINE User ID 取得・記入

### 公開設定
- [x] cloudflared quick tunnel 起動 → URL 取得
- [x] LINE Developers Console に Webhook URL 登録
- [x] Webhook 疎通テスト OK

### 動作確認
- [x] `python push_morning.py` 手動実行 → LINE 到達
- [x] ボタン押下 → reply メッセージ確認
- [x] SQLite に `taken_at` 記録確認

### 自動化
- [x] launchd plist 4個作成
- [x] launchd 登録（`launchctl bootstrap`）
- [ ] 翌朝7:30の自動送信成功 ← **明朝確認**

### 品質
- [x] `/quality-gate` 実行 → CRITICAL/HIGH 対応（F1〜F4 適用済み）

### 商用化検討時に追加対応する項目（Phase 2 メモ）
- [ ] Webhook destination 検証（複数チャネル運用時）
- [ ] user_id allowlist + 友だち登録 opt-in フロー
- [ ] Replay 攻撃対策（timestamp 検証 + webhookEventId 重複排除）
- [ ] レート制限導入（slowapi or Cloudflare WAF）
- [ ] ログPIIマスク（user_id フル値、postback data の隠蔽）
- [ ] cloudflared named tunnel 移行（URL固定）
- [ ] Channel Access Token v2.1（有効期限付き）+ JWT動的発行
- [ ] SQLite → PostgreSQL 移行（マルチユーザ前提）
- [ ] Repository パターン導入（テナント境界強制）
- [ ] タイムゾーン aware 化（`ZoneInfo("Asia/Tokyo")` 統一）
- [ ] 観測性（structlog + Sentry + UptimeRobot）
- [ ] 薬機法・個人情報保護法 ADR（弁護士確認）
- [ ] テストコード追加（最低5件: `verify_signature` 3ケース、`mark_taken` 二重防止、`/callback` 401、Flex構造、夜push条件）
- [ ] Python 3.9.6 → 3.12+ 移行（dotenv CVE-2026-28684 完全解消、3.9はEOL済み）

---

## 設計上の判断ログ

| 日時 | 判断 | 理由 |
|---|---|---|
| 2026-05-02 | LINE Notify ではなく Messaging API 採用 | LINE Notify は 2025-03-31 で終了済み |
| 2026-05-02 | named tunnel ではなく quick tunnel 採用 | Cloudflare アカウント・ドメインなし。quick tunnel で十分実用 |
| 2026-05-02 | TDD/full-pipeline ではなく直接実装 + 後段 quality-gate | 外部 API 依存が大きく TDD のモック地獄回避。設計は会話で固まり済み |
| 2026-05-02 | Phase 1 は自分用 MVP に限定、商用化（マルチユーザ・薬機法）は Phase 2 | 動くものを先に作って商用化議論を具体化する方が早い |
| 2026-05-02 | リマインド最大2回（7:30 + 22:00 の条件送信）に決定 | ユーザー希望。深夜多発を回避 |
| 2026-05-02 | quality-gate 後、F1-F4 のみ適用、商用化向け項目（10件）は Phase 2 へ | 個人MVPで実害のない項目（destination検証、replay対策、レート制限など）に時間使わない判断 |
| 2026-05-02 | python-dotenv 1.2.1 で固定（CVE-2026-28684 残） | Python 3.9.6 制約。CVEは `set_key`/`unset_key` のみ影響、本コードは `load_dotenv` のみ使用のため非到達 |
| 2026-05-02 | fastapi 0.128.8 + starlette 0.49.3 採用 | starlette 0.49.3 は CVE-2024-47874 / CVE-2025-54121 両方解消、Python 3.9 互換最新 |

---

## quality-gate 結果サマリー（2026-05-02 実施）

9エージェント並列レビュー実施。**統合判定: CONDITIONAL GO（個人MVPとして）**。

### 適用した修正（F1〜F4）
- **F1**: 依存パッケージCVE修正（fastapi 0.115→0.128.8、starlette 0.38.6→0.49.3、httpx 0.27.2→0.28.1、dotenv 1.0.1→1.2.1、uvicorn 0.30.6→0.34.3）
- **F2**: `line_api.py` に起動時 fail-fast バリデーション追加（必須env未設定で `RuntimeError`）
- **F3**: `db.py` の `mark_taken` を `INSERT...ON CONFLICT DO UPDATE WHERE taken_at IS NULL` に統合（TOCTOU race fix）+ `upsert_pushed`/`upsert_reminded` を `_upsert_timestamp` で DRY化 + `data/` ディレクトリ自動作成
- **F4**: 本ドキュメントに「運用チートシート」「cloudflared URL更新手順」「Token再発行手順」を追加

### 採用しなかった指摘の理由
- **destination 検証 / user_id allowlist**: シングルユーザー前提のため不要（Phase 2チェックリスト記録）
- **Replay 攻撃対策**: 個人用途で実害なし（同上）
- **レート制限**: cloudflared 経由で個人向けトラフィックのみ（同上）
- **アーキテクチャ大改造**: 500行のMVPには過剰（refactor-cleaner も同意）
- **接続プール / aiosqlite**: 1日2回の用途で過剰（performance-reviewer も同意）
- **`hmac.new` 不在指摘**: 誤検知（Python標準API）。E2Eテストで動作確認済み

---

## 更新履歴
- 2026-05-02: 初版作成。èªå®ãµã¼ãã¼ 環境確認まで完了、前提セットアップ手順をユーザーに依頼中。
- 2026-05-02 (続): セットアップ完了 → 動作確認 → /quality-gate 実施 → F1〜F4 適用完了。Phase 1 MVP 稼働開始。
