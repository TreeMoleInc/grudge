"""The social graph: sending/accepting/declining/cancelling friend requests,
and unfriending. See services/visibility.py for the separate two-tier
visibility-settings half.
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.models.friend import Friend, FriendRequest, FriendVisibilityOverride


class CannotFriendSelfError(Exception):
    pass


class AlreadyFriendsError(Exception):
    pass


class DuplicatePendingRequestError(Exception):
    pass


class RequestNotFoundError(Exception):
    pass


class NotFriendsError(Exception):
    pass


async def are_friends(db: AsyncSession, *, user_id: uuid.UUID, other_user_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(Friend.id).where(Friend.user_id == user_id, Friend.friend_user_id == other_user_id)
    )
    return result.scalar_one_or_none() is not None


async def send_request(
    db: AsyncSession, *, from_user_id: uuid.UUID, to_user_id: uuid.UUID
) -> FriendRequest:
    if from_user_id == to_user_id:
        raise CannotFriendSelfError("You cannot send a friend request to yourself.")
    if await are_friends(db, user_id=from_user_id, other_user_id=to_user_id):
        raise AlreadyFriendsError("You are already friends with this user.")

    existing = await db.execute(
        select(FriendRequest.id).where(
            or_(
                and_(
                    FriendRequest.from_user_id == from_user_id,
                    FriendRequest.to_user_id == to_user_id,
                ),
                and_(
                    FriendRequest.from_user_id == to_user_id,
                    FriendRequest.to_user_id == from_user_id,
                ),
            )
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise DuplicatePendingRequestError(
            "A pending request already exists between you and this user."
        )

    request = FriendRequest(from_user_id=from_user_id, to_user_id=to_user_id)
    db.add(request)
    await db.flush()
    return request


async def accept_request(
    db: AsyncSession, *, request_id: uuid.UUID, current_user_id: uuid.UUID
) -> uuid.UUID:
    """Returns the other party's user_id (the new friend, from the
    accepting user's perspective) so the router can build its response
    without a second lookup.
    """
    request = await db.get(FriendRequest, request_id)
    if request is None or request.to_user_id != current_user_id:
        raise RequestNotFoundError("No pending request with that ID was found for you.")

    db.add(Friend(user_id=request.from_user_id, friend_user_id=request.to_user_id))
    db.add(Friend(user_id=request.to_user_id, friend_user_id=request.from_user_id))
    await db.delete(request)
    await db.flush()
    return request.from_user_id


async def remove_request(
    db: AsyncSession, *, request_id: uuid.UUID, current_user_id: uuid.UUID
) -> None:
    """Cancel (by the sender) or decline (by the recipient) - same action
    from either side of the request.
    """
    request = await db.get(FriendRequest, request_id)
    if request is None or current_user_id not in (request.from_user_id, request.to_user_id):
        raise RequestNotFoundError("No request with that ID involves you.")
    await db.delete(request)
    await db.flush()


async def unfriend(db: AsyncSession, *, user_id: uuid.UUID, friend_user_id: uuid.UUID) -> None:
    """Deletes both directions of the friendship, plus both directions of
    any friend_visibility_overrides between the two (their allow-list join
    rows cascade via ON DELETE CASCADE) - a fresh re-friend starts clean at
    "default" rather than silently reactivating a stale override.
    """
    friend_rows = (
        (
            await db.execute(
                select(Friend).where(
                    or_(
                        and_(Friend.user_id == user_id, Friend.friend_user_id == friend_user_id),
                        and_(Friend.user_id == friend_user_id, Friend.friend_user_id == user_id),
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    if not friend_rows:
        raise NotFriendsError("You are not friends with this user.")
    for row in friend_rows:
        await db.delete(row)

    override_rows = (
        (
            await db.execute(
                select(FriendVisibilityOverride).where(
                    or_(
                        and_(
                            FriendVisibilityOverride.user_id == user_id,
                            FriendVisibilityOverride.friend_user_id == friend_user_id,
                        ),
                        and_(
                            FriendVisibilityOverride.user_id == friend_user_id,
                            FriendVisibilityOverride.friend_user_id == user_id,
                        ),
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    for override in override_rows:
        await db.delete(override)

    await db.flush()
