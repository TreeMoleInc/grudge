"""fetch_google_user is the thin, deliberately mockable seam between Authlib
and our upsert logic - tested here with fakes standing in for the OAuth
token, no real network or Authlib internals involved.

fetch_github_user had equivalent tests here (plus a FakeGithubClient) until
GitHub was dropped as a sign-in provider, 2026-09-04 (CLAUDE.md S2) - removed
along with the function itself rather than kept testing dead code.
"""

from grudge_backend.auth.providers import fetch_google_user


async def test_fetch_google_user_parses_userinfo():
    token = {"userinfo": {"sub": "12345", "email": "person@gmail.com", "picture": "http://p"}}
    info = await fetch_google_user(token)

    assert info.provider == "google"
    assert info.provider_user_id == "12345"
    assert info.email == "person@gmail.com"
    assert info.username == "person"
    assert info.avatar_url == "http://p"


async def test_fetch_google_user_username_falls_back_to_sub_when_no_email():
    token = {"userinfo": {"sub": "99999"}}
    info = await fetch_google_user(token)
    assert info.email is None
    assert info.username == "google_99999"
