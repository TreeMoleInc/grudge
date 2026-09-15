"""Deep end-to-end OAuth test: drive the REAL /auth/google/login -> callback
endpoints through the FastAPI app, with respx mocking only Google's own HTTP
endpoints (OIDC discovery, JWKS, token exchange) - unlike test_auth_flow.py
(which calls _login_or_create_user directly) and test_oauth_providers.py
(which unit-tests fetch_google_user with fakes), this is what actually
validates the real Authlib wiring: state/PKCE and the OIDC discovery + nonce +
id_token signature verification dance. Closed the gap originally tracked in
TODO.md ("Deeper OAuth end-to-end test missing"). Used to also cover GitHub's
plain authorization-code exchange the same way, until GitHub was dropped as a
sign-in provider, 2026-09-04 (CLAUDE.md S2).
"""

from __future__ import annotations

import json
import time
from urllib.parse import parse_qs, urlparse

import pytest
import respx
from authlib.jose import JsonWebKey
from authlib.jose import jwt as jose_jwt
from httpx import Response

from grudge_backend.config import settings

pytestmark = pytest.mark.integration

_TEST_RSA_KEY = JsonWebKey.generate_key("RSA", 2048, is_private=True)
_TEST_KID = "test-key"

_GOOGLE_DISCOVERY = {
    "issuer": "https://accounts.google.com",
    "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_endpoint": "https://oauth2.googleapis.com/token",
    "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
    "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
    "response_types_supported": ["code"],
    "subject_types_supported": ["public"],
    "id_token_signing_alg_values_supported": ["RS256"],
}


def _extract_query_param(url: str, name: str) -> str:
    return parse_qs(urlparse(url).query)[name][0]


def _google_jwks() -> dict:
    pub = json.loads(_TEST_RSA_KEY.as_json(is_private=False))
    pub.update(kid=_TEST_KID, alg="RS256", use="sig")
    return {"keys": [pub]}


def _sign_google_id_token(*, nonce: str, sub: str, email: str) -> str:
    """Signs a real RS256 id_token with a locally-generated test key, whose
    public half is served via the mocked jwks_uri below - so Authlib performs
    real signature verification against it, not a stub.
    """
    priv = json.loads(_TEST_RSA_KEY.as_json(is_private=True))
    priv.update(kid=_TEST_KID, alg="RS256")
    now = int(time.time())
    payload = {
        "iss": _GOOGLE_DISCOVERY["issuer"],
        "aud": settings.google_client_id,
        "sub": sub,
        "email": email,
        "iat": now,
        "exp": now + 300,
        "nonce": nonce,
    }
    token = jose_jwt.encode({"alg": "RS256", "kid": _TEST_KID}, payload, priv)
    return token.decode("utf-8")


@respx.mock
async def test_google_login_redirect_and_callback_full_flow(client):
    respx.get("https://accounts.google.com/.well-known/openid-configuration").mock(
        return_value=Response(200, json=_GOOGLE_DISCOVERY)
    )
    respx.get(_GOOGLE_DISCOVERY["jwks_uri"]).mock(return_value=Response(200, json=_google_jwks()))

    login_resp = await client.get("/auth/google/login", follow_redirects=False)
    assert login_resp.status_code in (302, 307)
    location = login_resp.headers["location"]
    assert location.startswith(_GOOGLE_DISCOVERY["authorization_endpoint"])
    state = _extract_query_param(location, "state")
    nonce = _extract_query_param(location, "nonce")

    id_token = _sign_google_id_token(nonce=nonce, sub="999", email="googler@example.com")
    respx.post(_GOOGLE_DISCOVERY["token_endpoint"]).mock(
        return_value=Response(
            200,
            json={
                "access_token": "goog-fake-token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "id_token": id_token,
            },
        )
    )

    callback_resp = await client.get(
        "/auth/google/callback",
        params={"code": "fake-code", "state": state},
        follow_redirects=False,
    )
    assert callback_resp.status_code in (302, 307)
    assert callback_resp.headers["location"] == settings.frontend_base_url
    assert settings.session_cookie_name in callback_resp.cookies

    me_resp = await client.get("/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["username"] == "googler"
