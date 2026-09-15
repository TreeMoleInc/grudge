"""A thin, deliberately mockable wrapper turning our sign-in provider's own
userinfo shape into a common ProviderUserInfo - this is the seam tests patch
instead of mocking Authlib's internals directly (see
tests/unit/test_oauth_providers.py).

fetch_github_user lived here until 2026-09-04, when GitHub was dropped as a
sign-in provider (CLAUDE.md S2) - removed along with it rather than kept
dead, since nothing calls it anymore.
"""

from __future__ import annotations

from typing import Any

from grudge_backend.schemas.auth import ProviderUserInfo


async def fetch_google_user(token: dict[str, Any]) -> ProviderUserInfo:
    """Authlib attaches a verified `userinfo` claims dict to the token response
    for OIDC providers (see auth/oauth.py) - no separate API call needed.
    """
    userinfo = token.get("userinfo") or {}
    sub = str(userinfo["sub"])
    email = userinfo.get("email")
    return ProviderUserInfo(
        provider="google",
        provider_user_id=sub,
        email=email,
        username=(email.split("@")[0] if email else None) or f"google_{sub}",
        avatar_url=userinfo.get("picture"),
    )
