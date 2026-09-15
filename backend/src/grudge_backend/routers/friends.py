from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.auth.dependencies import get_current_user
from grudge_backend.db import get_db
from grudge_backend.exceptions import bad_request, conflict, not_found
from grudge_backend.models.automaton import AutomatonVersion
from grudge_backend.models.friend import (
    Friend,
    FriendRequest,
    FriendSettingsAutomaton,
    FriendVisibilityOverrideAutomaton,
)
from grudge_backend.models.user import User
from grudge_backend.schemas.friend import (
    FriendAutomatonCodeRead,
    FriendProfileRead,
    FriendRead,
    FriendRequestCreate,
    FriendRequestRead,
    FriendSettingsRead,
    FriendSettingsUpdate,
    FriendVisibilityOverrideRead,
    FriendVisibilityOverrideUpdate,
    VisibleAutomatonSummary,
)
from grudge_backend.services import friends as friends_service
from grudge_backend.services import visibility as visibility_service

router = APIRouter(prefix="/friends", tags=["friends"])


async def _get_user_by_username(db: AsyncSession, *, username: str) -> User:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        raise not_found("User not found.")
    return user


async def _get_user(db: AsyncSession, *, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise not_found("User not found.")
    return user


# --- Settings (global) - literal paths registered before the parameterized
# /friends/{friend_user_id}/... routes below, defensively (FastAPI's typed
# uuid.UUID path param already fails to match "settings", but don't rely on
# that implicitly). ---


@router.get("/settings", response_model=FriendSettingsRead)
async def get_friend_settings(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> FriendSettingsRead:
    global_mode, allow_ids = await visibility_service.get_friend_settings_or_default(
        db, user_id=current_user.id
    )
    return FriendSettingsRead(global_mode=global_mode, automaton_ids=list(allow_ids))  # type: ignore[arg-type]


@router.patch("/settings", response_model=FriendSettingsRead)
async def update_friend_settings(
    payload: FriendSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FriendSettingsRead:
    updates = payload.model_dump(exclude_unset=True)

    if "automaton_ids" in updates and updates["automaton_ids"] is not None:
        try:
            await visibility_service.assert_all_owned(
                db, user_id=current_user.id, automaton_ids=updates["automaton_ids"]
            )
        except visibility_service.AutomataNotOwnedError as exc:
            raise bad_request(str(exc)) from exc

    settings = await visibility_service.get_or_create_friend_settings(db, user_id=current_user.id)
    if "global_mode" in updates and updates["global_mode"] is not None:
        settings.global_mode = updates["global_mode"]

    if "automaton_ids" in updates and updates["automaton_ids"] is not None:
        existing = await db.execute(
            select(FriendSettingsAutomaton).where(
                FriendSettingsAutomaton.user_id == current_user.id
            )
        )
        for row in existing.scalars().all():
            await db.delete(row)
        for automaton_id in updates["automaton_ids"]:
            db.add(FriendSettingsAutomaton(user_id=current_user.id, automaton_id=automaton_id))

    await db.commit()
    global_mode, allow_ids = await visibility_service.get_friend_settings_or_default(
        db, user_id=current_user.id
    )
    return FriendSettingsRead(global_mode=global_mode, automaton_ids=list(allow_ids))  # type: ignore[arg-type]


# --- Requests ---


@router.post("/requests", response_model=FriendRequestRead, status_code=201)
async def send_friend_request(
    payload: FriendRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FriendRequestRead:
    target = await _get_user_by_username(db, username=payload.username)
    try:
        request = await friends_service.send_request(
            db, from_user_id=current_user.id, to_user_id=target.id
        )
    except friends_service.CannotFriendSelfError as exc:
        await db.rollback()
        raise bad_request(str(exc)) from exc
    except (
        friends_service.AlreadyFriendsError,
        friends_service.DuplicatePendingRequestError,
    ) as exc:
        await db.rollback()
        raise conflict(str(exc)) from exc

    await db.commit()
    await db.refresh(request)
    return FriendRequestRead(
        id=request.id,
        from_user_id=request.from_user_id,
        from_username=current_user.username,
        to_user_id=request.to_user_id,
        to_username=target.username,
        created_at=request.created_at,
    )


@router.get("/requests/incoming", response_model=list[FriendRequestRead])
async def list_incoming_requests(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[FriendRequestRead]:
    result = await db.execute(
        select(FriendRequest, User.username)
        .join(User, User.id == FriendRequest.from_user_id)
        .where(FriendRequest.to_user_id == current_user.id)
    )
    return [
        FriendRequestRead(
            id=req.id,
            from_user_id=req.from_user_id,
            from_username=from_username,
            to_user_id=req.to_user_id,
            to_username=current_user.username,
            created_at=req.created_at,
        )
        for req, from_username in result.all()
    ]


@router.get("/requests/outgoing", response_model=list[FriendRequestRead])
async def list_outgoing_requests(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[FriendRequestRead]:
    result = await db.execute(
        select(FriendRequest, User.username)
        .join(User, User.id == FriendRequest.to_user_id)
        .where(FriendRequest.from_user_id == current_user.id)
    )
    return [
        FriendRequestRead(
            id=req.id,
            from_user_id=req.from_user_id,
            from_username=current_user.username,
            to_user_id=req.to_user_id,
            to_username=to_username,
            created_at=req.created_at,
        )
        for req, to_username in result.all()
    ]


@router.post("/requests/{request_id}/accept", response_model=FriendRead)
async def accept_friend_request(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FriendRead:
    try:
        from_user_id = await friends_service.accept_request(
            db, request_id=request_id, current_user_id=current_user.id
        )
    except friends_service.RequestNotFoundError as exc:
        await db.rollback()
        raise not_found(str(exc)) from exc

    await db.commit()
    new_friend = await _get_user(db, user_id=from_user_id)
    friend_row = (
        await db.execute(
            select(Friend).where(
                Friend.user_id == current_user.id, Friend.friend_user_id == new_friend.id
            )
        )
    ).scalar_one()
    return FriendRead(
        friend_user_id=new_friend.id,
        username=new_friend.username,
        avatar_url=new_friend.avatar_url,
        rating=new_friend.rating,
        friended_at=friend_row.created_at,
    )


@router.delete("/requests/{request_id}", status_code=204)
async def remove_friend_request(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await friends_service.remove_request(
            db, request_id=request_id, current_user_id=current_user.id
        )
    except friends_service.RequestNotFoundError as exc:
        await db.rollback()
        raise not_found(str(exc)) from exc
    await db.commit()


# --- Friends list / unfriend ---


@router.get("", response_model=list[FriendRead])
async def list_friends(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[FriendRead]:
    result = await db.execute(
        select(Friend, User)
        .join(User, User.id == Friend.friend_user_id)
        .where(Friend.user_id == current_user.id)
    )
    return [
        FriendRead(
            friend_user_id=user.id,
            username=user.username,
            avatar_url=user.avatar_url,
            rating=user.rating,
            friended_at=friend_row.created_at,
        )
        for friend_row, user in result.all()
    ]


@router.delete("/{friend_user_id}", status_code=204)
async def remove_friend(
    friend_user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await friends_service.unfriend(db, user_id=current_user.id, friend_user_id=friend_user_id)
    except friends_service.NotFriendsError as exc:
        await db.rollback()
        raise not_found(str(exc)) from exc
    await db.commit()


# --- Friend profile (visibility-filtered) ---


@router.get("/{friend_user_id}/profile", response_model=FriendProfileRead)
async def get_friend_profile(
    friend_user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FriendProfileRead:
    if not await friends_service.are_friends(
        db, user_id=current_user.id, other_user_id=friend_user_id
    ):
        raise not_found("You are not friends with this user.")

    friend = await _get_user(db, user_id=friend_user_id)
    visible_automata = await visibility_service.get_visible_automata(
        db, owner_user_id=friend_user_id, viewer_user_id=current_user.id
    )
    return FriendProfileRead(
        user_id=friend.id,
        username=friend.username,
        avatar_url=friend.avatar_url,
        rating=friend.rating,
        ranked_tournaments_played=friend.ranked_tournaments_played,
        visible_automata=[VisibleAutomatonSummary(id=a.id, name=a.name) for a in visible_automata],
    )


@router.get(
    "/{friend_user_id}/automata/{automaton_id}/code", response_model=FriendAutomatonCodeRead
)
async def get_friend_automaton_code(
    friend_user_id: uuid.UUID,
    automaton_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FriendAutomatonCodeRead:
    """The live code of a friend's active version - not a frozen tournament
    snapshot, so this is a "current state" view, consistent with how the
    Automata page shows your own current code. Re-resolves visibility fresh
    server-side rather than trusting that `automaton_id` came from a prior
    /profile response, so a non-visible automaton can't be fetched by guessing
    its id.
    """
    if not await friends_service.are_friends(
        db, user_id=current_user.id, other_user_id=friend_user_id
    ):
        raise not_found("You are not friends with this user.")

    visible_automata = await visibility_service.get_visible_automata(
        db, owner_user_id=friend_user_id, viewer_user_id=current_user.id
    )
    automaton = next((a for a in visible_automata if a.id == automaton_id), None)
    if automaton is None or automaton.active_version_id is None:
        raise not_found("Automaton not found.")

    version = await db.get(AutomatonVersion, automaton.active_version_id)
    if version is None:
        raise not_found("Automaton not found.")
    return FriendAutomatonCodeRead(code=version.code)


# --- Per-friend visibility override ---


@router.get("/{friend_user_id}/visibility-override", response_model=FriendVisibilityOverrideRead)
async def get_visibility_override(
    friend_user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FriendVisibilityOverrideRead:
    if not await friends_service.are_friends(
        db, user_id=current_user.id, other_user_id=friend_user_id
    ):
        raise not_found("You are not friends with this user.")

    mode, allow_ids = await visibility_service.get_override_or_default(
        db, user_id=current_user.id, friend_user_id=friend_user_id
    )
    return FriendVisibilityOverrideRead(
        friend_user_id=friend_user_id, mode=mode, automaton_ids=list(allow_ids)
    )  # type: ignore[arg-type]


@router.patch("/{friend_user_id}/visibility-override", response_model=FriendVisibilityOverrideRead)
async def update_visibility_override(
    friend_user_id: uuid.UUID,
    payload: FriendVisibilityOverrideUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FriendVisibilityOverrideRead:
    if not await friends_service.are_friends(
        db, user_id=current_user.id, other_user_id=friend_user_id
    ):
        raise not_found("You are not friends with this user.")

    updates = payload.model_dump(exclude_unset=True)

    if "automaton_ids" in updates and updates["automaton_ids"] is not None:
        try:
            await visibility_service.assert_all_owned(
                db, user_id=current_user.id, automaton_ids=updates["automaton_ids"]
            )
        except visibility_service.AutomataNotOwnedError as exc:
            raise bad_request(str(exc)) from exc

    override = await visibility_service.get_or_create_override(
        db, user_id=current_user.id, friend_user_id=friend_user_id
    )
    if "mode" in updates and updates["mode"] is not None:
        override.mode = updates["mode"]

    if "automaton_ids" in updates and updates["automaton_ids"] is not None:
        existing = await db.execute(
            select(FriendVisibilityOverrideAutomaton).where(
                FriendVisibilityOverrideAutomaton.override_id == override.id
            )
        )
        for row in existing.scalars().all():
            await db.delete(row)
        for automaton_id in updates["automaton_ids"]:
            db.add(
                FriendVisibilityOverrideAutomaton(
                    override_id=override.id, automaton_id=automaton_id
                )
            )

    await db.commit()
    mode, allow_ids = await visibility_service.get_override_or_default(
        db, user_id=current_user.id, friend_user_id=friend_user_id
    )
    return FriendVisibilityOverrideRead(
        friend_user_id=friend_user_id, mode=mode, automaton_ids=list(allow_ids)
    )  # type: ignore[arg-type]
