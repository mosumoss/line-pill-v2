"""LINE Messaging API Webhook ハンドラ。

postback アクション "take:{serving_id}" を受け取り、服薬記録を行い
かわいい応援メッセージを reply で返す。LIFF UI を開かずに完結する。

エンドポイント: POST /webhook (LINE Developer Console の Webhook URL に設定)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from db import get_db
from line_api import ENCOURAGE_MESSAGES, reply_text
from repositories.servings import mark_taken
from repositories.users import get_or_create_user

router = APIRouter()

LINE_CHANNEL_SECRET: str = os.environ.get("LINE_CHANNEL_SECRET", "")


def _verify_signature(body: bytes, signature: str) -> bool:
    """LINE Webhook の署名検証 (HMAC-SHA256)。"""
    if not LINE_CHANNEL_SECRET or not signature:
        return False
    digest = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def _pick_message(taken: bool) -> str:
    """応援メッセージを1つ選ぶ（taken=False は「既に記録済み」系）。"""
    import random
    if not taken:
        return "もう記録済みですよ💊 引き続き頑張りましょう✨"
    return random.choice(ENCOURAGE_MESSAGES)


@router.post("/webhook")
async def webhook(
    request: Request,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    x_line_signature: Annotated[str, Header(alias="X-Line-Signature")] = "",
) -> dict:
    """LINE Messaging API webhook 受信口。

    署名検証 → events をループ → postback を処理。
    LINE は 2xx を期待するので、エラーがあっても 200 を返してログに残す方針。
    """
    body = await request.body()

    if not _verify_signature(body, x_line_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(body)
    for event in payload.get("events", []):
        if event.get("type") != "postback":
            continue
        await _handle_postback(event, conn)

    return {"ok": True}


async def _handle_postback(event: dict, conn: sqlite3.Connection) -> None:
    data: str = event.get("postback", {}).get("data", "")
    reply_token: str = event.get("replyToken", "")
    line_user_id: str = event.get("source", {}).get("userId", "")

    if not data.startswith("take:") or not reply_token or not line_user_id:
        return

    try:
        serving_id = int(data[len("take:"):])
    except ValueError:
        return

    user = get_or_create_user(conn, line_user_id)
    taken = mark_taken(conn, user_id=user.id, serving_id=serving_id)
    reply_text(reply_token, _pick_message(taken))
