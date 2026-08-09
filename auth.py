"""LIFF ID token 検証 — LINE JWKs を使った RS256 署名検証。

公開関数:
- verify_id_token(token, *, channel_id=None) -> dict  ← claims を返す
- TokenVerificationError  ← 検証失敗時の例外

JWKs は TTLCache (1時間) でキャッシュする。
FastAPI Depends への組み込みは routers/api.py が担う。
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from cachetools import TTLCache
from jose import JWTError
from jose import jwt as jose_jwt

LIFF_CHANNEL_ID: str = os.environ.get("LIFF_CHANNEL_ID", "")
LINE_JWKS_URL: str = "https://api.line.me/oauth2/v2.1/certs"

# JWKs: 1時間 TTL、最大1エントリ (LINE JWKs は1つのエンドポイント)
_jwks_cache: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=1, ttl=3600)

_CACHE_KEY = "line_jwks"


class TokenVerificationError(Exception):
    """LIFF ID token 検証失敗。詳細メッセージを含む。"""


# ---------- JWKs 取得 ----------

def _get_jwks() -> dict[str, Any]:
    """LINE JWKs を取得。TTL キャッシュ済みなので通常は1回のみリクエスト。"""
    if _CACHE_KEY in _jwks_cache:
        return _jwks_cache[_CACHE_KEY]
    resp = httpx.get(LINE_JWKS_URL, timeout=5.0)
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    _jwks_cache[_CACHE_KEY] = data
    return data


def _find_jwk(jwks: dict[str, Any], kid: str | None) -> dict[str, Any] | None:
    """kid に一致する JWK を返す。なければ None。"""
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None


# ---------- 公開 API ----------

def verify_id_token(
    token: str,
    *,
    channel_id: str | None = None,
) -> dict[str, Any]:
    """LIFF ID token (JWT) を検証し、ペイロード claims を返す。

    Args:
        token: LINE LIFF が発行した ID token
        channel_id: 検証する aud 値。省略時は環境変数 LIFF_CHANNEL_ID を使用

    Returns:
        JWT ペイロード (sub, name, picture, aud, exp 等)

    Raises:
        TokenVerificationError:
            - LIFF_CHANNEL_ID が未設定
            - トークンヘッダー不正
            - JWKs 取得失敗
            - kid 不明
            - 署名不正 / 期限切れ / aud 不一致
    """
    aud = channel_id or LIFF_CHANNEL_ID
    if not aud:
        raise TokenVerificationError(
            "LIFF_CHANNEL_ID is not configured. "
            "Set the LIFF_CHANNEL_ID environment variable or pass channel_id."
        )

    # ヘッダーから kid を取得 (署名鍵の選択に使用)
    try:
        header = jose_jwt.get_unverified_header(token)
    except JWTError as exc:
        raise TokenVerificationError(f"Invalid token header: {exc}") from exc

    kid = header.get("kid")

    # JWKs 取得 (キャッシュ優先)
    try:
        jwks = _get_jwks()
    except Exception as exc:
        raise TokenVerificationError(f"Failed to fetch JWKs: {exc}") from exc

    jwk = _find_jwk(jwks, kid)
    if jwk is None:
        raise TokenVerificationError(
            f"Unknown key id: {kid!r}. "
            "The token may have been issued with a rotated key — retry after cache TTL."
        )

    # 署名・有効期限・audience を検証
    # LINE Login の LIFF ID Token は ES256、Messaging API 系は RS256 を使うため両方許可
    try:
        claims: dict[str, Any] = jose_jwt.decode(
            token,
            jwk,
            algorithms=["ES256", "RS256"],
            audience=aud,
        )
    except JWTError as exc:
        raise TokenVerificationError(f"Token verification failed: {exc}") from exc

    return claims
