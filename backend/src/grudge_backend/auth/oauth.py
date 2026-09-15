"""Authlib client registration for our sign-in provider. Authorization-code
flow + state/CSRF + PKCE + OIDC discovery is exactly the kind of
security-sensitive plumbing not worth hand-rolling.

GitHub was registered here too until 2026-09-04, when it was dropped as a
sign-in provider by product decision (CLAUDE.md S2) in favor of a single
provider. Discord remains a plausible future addition given the
tournament/social angle - if it's added, register it the same way this file
registered GitHub before removal.
"""

from __future__ import annotations

from authlib.integrations.starlette_client import OAuth

from grudge_backend.config import settings

oauth = OAuth()

# OIDC discovery - Google's metadata endpoint tells Authlib the token/authorize/
# userinfo URLs and the JWKS used to verify the id_token, so the token response
# from authorize_access_token() comes back with a verified `userinfo` claims dict
# already attached (see auth/providers.py:fetch_google_user).
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)
