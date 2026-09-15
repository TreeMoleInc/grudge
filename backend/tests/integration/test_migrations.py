"""Confirms the circular FK (automata.active_version_id <-> automaton_versions
.automaton_id) is actually enforced at the DB level, not just present in the
ORM models - via the already-applied migration (see conftest.py's
session-scoped _migrated_schema fixture) plus a real insert/flush.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from grudge_backend.services.automata import create_automaton_with_first_version

pytestmark = pytest.mark.integration


async def test_schema_has_expected_tables(db_session):
    result = await db_session.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    )
    tables = {row[0] for row in result.fetchall()}
    assert {
        "users",
        "auth_identities",
        "sessions",
        "automaton_folders",
        "automata",
        "automaton_versions",
        "tournament_entries",
        "matches",
        "rating_history",
        "notifications",
    } <= tables


async def test_active_version_fk_is_enforced(db_session, user):
    automaton, version = await create_automaton_with_first_version(
        db_session,
        user_id=user.id,
        name="Bot",
        folder_id=None,
        code="def decide(history):\n    return COOPERATE\n",
    )
    assert automaton.active_version_id == version.id

    # Pointing active_version_id at a version that doesn't exist must violate
    # the deferred FK added in migration 0004 - proves it's really there.
    automaton.active_version_id = uuid.uuid4()
    with pytest.raises(IntegrityError):
        await db_session.flush()
