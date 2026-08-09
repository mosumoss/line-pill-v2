"""auth.py (LIFF ID token 検証) のテスト。

TDD: GREEN実装は auth.py。
- python-jose[cryptography] でRS256署名検証
- cachetools TTLCache で JWKs をキャッシュ
- respx で httpx.get をモック
"""
from __future__ import annotations

import time

import httpx
import pytest
import respx
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from freezegun import freeze_time
from jose import jwk as jose_jwk
from jose import jwt as jose_jwt

import auth
from auth import TokenVerificationError, verify_id_token

# テスト用 LIFF Channel ID
TEST_CHANNEL_ID = "test-channel-id-99999"
LINE_JWKS_URL = "https://api.line.me/oauth2/v2.1/certs"
TEST_KID = "test-key-001"


# ---------- Fixtures ----------

@pytest.fixture(scope="module")
def rsa_keypair() -> tuple[bytes, dict]:
    """RSA 2048 キーペア (private_pem, jwk_dict)。モジュール内で1回生成。"""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    jwk_dict = jose_jwk.construct(public_pem, algorithm="RS256").to_dict()
    jwk_dict["kid"] = TEST_KID
    jwk_dict["use"] = "sig"
    jwk_dict["alg"] = "RS256"
    return private_pem, jwk_dict


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    """各テスト前後に JWKs キャッシュをクリアして独立性を保つ。"""
    auth._jwks_cache.clear()
    yield
    auth._jwks_cache.clear()


def _make_token(
    private_pem: bytes,
    kid: str,
    extra_claims: dict | None = None,
    *,
    aud: str = TEST_CHANNEL_ID,
    exp_offset: int = 3600,
) -> str:
    """テスト用 JWT を生成する。exp_offset 秒後に期限切れ。"""
    now = int(time.time())
    claims = {
        "iss": "https://access.line.me",
        "sub": "U_LINE_TESTUSER_001",
        "aud": aud,
        "iat": now,
        "exp": now + exp_offset,
        "name": "テストユーザー",
    }
    if extra_claims:
        claims.update(extra_claims)
    return jose_jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": kid})


# ---------- Valid token ----------

class TestValidToken:
    def test_returns_claims_for_valid_token(self, rsa_keypair: tuple) -> None:
        private_pem, jwk_dict = rsa_keypair
        token = _make_token(private_pem, TEST_KID)
        with respx.mock:
            respx.get(LINE_JWKS_URL).mock(
                return_value=httpx.Response(200, json={"keys": [jwk_dict]})
            )
            claims = verify_id_token(token, channel_id=TEST_CHANNEL_ID)
        assert claims["sub"] == "U_LINE_TESTUSER_001"

    def test_claims_contain_aud(self, rsa_keypair: tuple) -> None:
        private_pem, jwk_dict = rsa_keypair
        token = _make_token(private_pem, TEST_KID)
        with respx.mock:
            respx.get(LINE_JWKS_URL).mock(
                return_value=httpx.Response(200, json={"keys": [jwk_dict]})
            )
            claims = verify_id_token(token, channel_id=TEST_CHANNEL_ID)
        assert claims["aud"] == TEST_CHANNEL_ID

    def test_claims_contain_name(self, rsa_keypair: tuple) -> None:
        private_pem, jwk_dict = rsa_keypair
        token = _make_token(private_pem, TEST_KID, {"name": "山田太郎"})
        with respx.mock:
            respx.get(LINE_JWKS_URL).mock(
                return_value=httpx.Response(200, json={"keys": [jwk_dict]})
            )
            claims = verify_id_token(token, channel_id=TEST_CHANNEL_ID)
        assert claims["name"] == "山田太郎"


# ---------- Token errors ----------

class TestInvalidToken:
    def test_expired_token_raises_error(self, rsa_keypair: tuple) -> None:
        private_pem, jwk_dict = rsa_keypair
        with freeze_time("2026-05-06 07:00:00"):
            token = _make_token(private_pem, TEST_KID, exp_offset=60)

        with freeze_time("2026-05-06 07:02:00"):  # 2分後 → 期限切れ
            with respx.mock:
                respx.get(LINE_JWKS_URL).mock(
                    return_value=httpx.Response(200, json={"keys": [jwk_dict]})
                )
                with pytest.raises(TokenVerificationError, match="expired|Signature"):
                    verify_id_token(token, channel_id=TEST_CHANNEL_ID)

    def test_wrong_audience_raises_error(self, rsa_keypair: tuple) -> None:
        private_pem, jwk_dict = rsa_keypair
        token = _make_token(private_pem, TEST_KID, aud="wrong-channel-id")
        with respx.mock:
            respx.get(LINE_JWKS_URL).mock(
                return_value=httpx.Response(200, json={"keys": [jwk_dict]})
            )
            with pytest.raises(TokenVerificationError):
                verify_id_token(token, channel_id=TEST_CHANNEL_ID)

    def test_tampered_token_raises_error(self, rsa_keypair: tuple) -> None:
        private_pem, jwk_dict = rsa_keypair
        token = _make_token(private_pem, TEST_KID)
        tampered = token[:-5] + "XXXXX"
        with respx.mock:
            respx.get(LINE_JWKS_URL).mock(
                return_value=httpx.Response(200, json={"keys": [jwk_dict]})
            )
            with pytest.raises(TokenVerificationError):
                verify_id_token(tampered, channel_id=TEST_CHANNEL_ID)

    def test_unknown_kid_raises_error(self, rsa_keypair: tuple) -> None:
        private_pem, jwk_dict = rsa_keypair
        token = _make_token(private_pem, "unknown-kid-xyz")
        with respx.mock:
            respx.get(LINE_JWKS_URL).mock(
                return_value=httpx.Response(200, json={"keys": [jwk_dict]})
            )
            with pytest.raises(TokenVerificationError, match="Unknown key"):
                verify_id_token(token, channel_id=TEST_CHANNEL_ID)

    def test_malformed_token_raises_error(self, rsa_keypair: tuple) -> None:
        with respx.mock:
            respx.get(LINE_JWKS_URL).mock(
                return_value=httpx.Response(200, json={"keys": []})
            )
            with pytest.raises(TokenVerificationError):
                verify_id_token("not.a.jwt", channel_id=TEST_CHANNEL_ID)

    def test_missing_channel_id_raises_error(self, rsa_keypair: tuple) -> None:
        private_pem, jwk_dict = rsa_keypair
        token = _make_token(private_pem, TEST_KID)
        with pytest.raises(TokenVerificationError, match="LIFF_CHANNEL_ID"):
            verify_id_token(token, channel_id="")


# ---------- JWKs caching ----------

class TestJwksCaching:
    def test_jwks_fetched_once_for_multiple_verifications(
        self, rsa_keypair: tuple
    ) -> None:
        """JWKs は最初の1回だけ取得し、以降はキャッシュを使うこと。"""
        private_pem, jwk_dict = rsa_keypair
        fetch_count = 0

        def counting_jwks_handler(request: httpx.Request) -> httpx.Response:
            nonlocal fetch_count
            fetch_count += 1
            return httpx.Response(200, json={"keys": [jwk_dict]})

        t1 = _make_token(private_pem, TEST_KID)
        t2 = _make_token(private_pem, TEST_KID)

        with respx.mock:
            respx.get(LINE_JWKS_URL).mock(side_effect=counting_jwks_handler)
            verify_id_token(t1, channel_id=TEST_CHANNEL_ID)
            verify_id_token(t2, channel_id=TEST_CHANNEL_ID)

        assert fetch_count == 1, f"JWKs should be fetched once, got {fetch_count}"

    def test_jwks_fetch_failure_raises_error(self, rsa_keypair: tuple) -> None:
        private_pem, _ = rsa_keypair
        token = _make_token(private_pem, TEST_KID)
        with respx.mock:
            respx.get(LINE_JWKS_URL).mock(
                return_value=httpx.Response(500)
            )
            with pytest.raises(TokenVerificationError, match="JWKs"):
                verify_id_token(token, channel_id=TEST_CHANNEL_ID)
