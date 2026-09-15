"""CORS is required for the Phase 4 frontend (a different port = a different
origin, even on localhost) to make credentialed fetch/WebSocket calls at all -
see main.py's CORSMiddleware registration and the Phase 4 plan.
"""

from __future__ import annotations

import pytest

from grudge_backend.config import settings

pytestmark = pytest.mark.integration


async def test_cross_origin_request_gets_credentialed_cors_headers(client):
    resp = await client.get("/me", headers={"Origin": settings.frontend_base_url})
    assert resp.headers.get("access-control-allow-origin") == settings.frontend_base_url
    assert resp.headers.get("access-control-allow-credentials") == "true"


async def test_disallowed_origin_gets_no_cors_headers(client):
    resp = await client.get("/me", headers={"Origin": "http://evil.example.com"})
    assert "access-control-allow-origin" not in resp.headers
