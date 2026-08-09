"""LINE Messaging API クライアント。

公開関数:
- push_text(line_user_id, slot) — プレーンテキスト版（旧API互換）
- push_reminder(line_user_id, slot, serving_id) — 服用ボタン付き Flex Message
- reply_text(reply_token, text) — Webhook の reply API でテキスト返信

公開定数:
- ENCOURAGE_MESSAGES — 服薬完了時のかわいい応援メッセージ
"""
from __future__ import annotations

import os

import httpx

LINE_CHANNEL_ACCESS_TOKEN: str = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
_LINE_API_BASE = "https://api.line.me/v2/bot"


# 服薬完了時のかわいい応援メッセージ（ランダムに1つ送る）
ENCOURAGE_MESSAGES: list[str] = [
    "記録しました！未来の自分のために、明日も頑張りましょう🎶",
    "えらい！継続は美髪の道です✨",
    "ナイス！コツコツ続けるあなたが素敵です🌸",
    "記録完了！理想の自分に一歩前進です💫",
    "OK！未来の素敵な髪のために、ファイト🌟",
    "服薬記録できました！えらいえらい〜🎀",
    "やったね！毎日の積み重ねが未来を作ります🌷",
    "今日もえらい！明日もこの調子でいきましょう💕",
]


def _reminder_text(slot: str) -> str:
    if slot == "morning":
        return "おはようございます！朝の薬の時間です🌅"
    return "お疲れ様です！夜の薬の時間です🌙"


def push_text(line_user_id: str, slot: str) -> None:
    """プレーンテキストのリマインダー（旧API互換）。"""
    _push(line_user_id, [{"type": "text", "text": _reminder_text(slot)}])


def push_reminder(
    line_user_id: str,
    slot: str,
    serving_id: int,
    *,
    is_followup: bool = False,
) -> None:
    """服用ボタン付きの Flex Message を送信する。

    ボタンタップで postback アクションが発火し、webhook 経由で
    服薬記録 + 応援メッセージ返信が行われる（UI は開かない）。

    is_followup=True のときは「飲み忘れリマインダー」用に
    タイトル・文言を変える（ボタン動作は同じ）。
    """
    if is_followup:
        slot_label = "💭 飲み忘れリマインダー"
        body_text = (
            f"今日の{'朝' if slot == 'morning' else '夜'}の薬、"
            "まだ飲んでないみたいです🤔 忘れてませんか？"
        )
    else:
        slot_label = "朝の薬 🌅" if slot == "morning" else "夜の薬 🌙"
        body_text = _reminder_text(slot)
    # 以降は flex 構築（slot_label / body_text を使う）
    return _push_reminder_flex(line_user_id, slot_label, body_text, slot, serving_id)


def _push_reminder_flex(
    line_user_id: str,
    slot_label: str,
    body_text: str,
    slot: str,
    serving_id: int,
) -> None:
    _ = slot  # 互換のため引数は受けるが内部利用なし

    flex_contents = {
        "type": "bubble",
        "size": "kilo",
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "text",
                    "text": slot_label,
                    "weight": "bold",
                    "size": "lg",
                    "color": "#06c755",
                },
                {
                    "type": "text",
                    "text": body_text,
                    "wrap": True,
                    "size": "sm",
                    "color": "#424242",
                },
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#06c755",
                    "action": {
                        "type": "postback",
                        "label": "💊 服用しました",
                        "data": f"take:{serving_id}",
                        "displayText": "💊 服用しました",
                    },
                }
            ],
        },
    }

    _push(line_user_id, [
        {
            "type": "flex",
            "altText": body_text,
            "contents": flex_contents,
        }
    ])


def reply_text(reply_token: str, text: str) -> None:
    """Webhook イベントの replyToken を使ってテキスト返信する。"""
    httpx.post(
        f"{_LINE_API_BASE}/message/reply",
        headers={
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": text}],
        },
        timeout=10.0,
    ).raise_for_status()


def _push(line_user_id: str, messages: list[dict]) -> None:
    resp = httpx.post(
        f"{_LINE_API_BASE}/message/push",
        headers={
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"to": line_user_id, "messages": messages},
        timeout=10.0,
    )
    resp.raise_for_status()
