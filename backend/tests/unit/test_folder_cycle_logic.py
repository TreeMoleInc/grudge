"""Pure-logic tests for services.folders.find_cycle - an in-memory dict stands in
for the DB-backed parent lookup, so this covers the graph-walk algorithm itself
with no database involved.
"""

import uuid

from grudge_backend.services.folders import find_cycle

A, B, C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def _lookup_from(tree: dict[uuid.UUID, uuid.UUID | None]):
    async def get_parent(folder_id: uuid.UUID) -> uuid.UUID | None:
        return tree.get(folder_id)

    return get_parent


async def test_new_parent_none_is_never_a_cycle():
    assert await find_cycle(folder_id=A, new_parent_id=None, get_parent=_lookup_from({})) is False


async def test_self_parent_is_a_cycle():
    assert await find_cycle(folder_id=A, new_parent_id=A, get_parent=_lookup_from({})) is True


async def test_unrelated_parent_is_not_a_cycle():
    # B has no parent, A is trying to move under B - fine, no relation at all
    tree = {B: None}
    assert await find_cycle(folder_id=A, new_parent_id=B, get_parent=_lookup_from(tree)) is False


async def test_direct_two_node_cycle_detected():
    # B's parent is A; moving A under B would create A -> B -> A
    tree = {B: A}
    assert await find_cycle(folder_id=A, new_parent_id=B, get_parent=_lookup_from(tree)) is True


async def test_deeper_cycle_detected():
    # C's parent is B, B's parent is A; moving A under C would create A -> C -> B -> A
    tree = {C: B, B: A}
    assert await find_cycle(folder_id=A, new_parent_id=C, get_parent=_lookup_from(tree)) is True


async def test_deep_non_cycle_chain_allowed():
    # C's parent is B, B has no parent; moving A under C is fine (A isn't in that chain)
    tree = {C: B, B: None}
    assert await find_cycle(folder_id=A, new_parent_id=C, get_parent=_lookup_from(tree)) is False


async def test_defensive_guard_does_not_infinite_loop_on_pre_existing_cycle():
    # B <-> C already form a cycle (shouldn't be possible via the API, but the
    # walk must not hang forever if it somehow happens) - A isn't part of it.
    tree = {B: C, C: B}
    result = await find_cycle(folder_id=A, new_parent_id=B, get_parent=_lookup_from(tree))
    assert result is False
