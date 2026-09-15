from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

GlobalMode = Literal["show", "hide", "specific"]
OverrideMode = Literal["default", "show", "hide", "specific"]


class FriendRequestCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)


class FriendRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_user_id: uuid.UUID
    from_username: str
    to_user_id: uuid.UUID
    to_username: str
    created_at: datetime


class FriendRead(BaseModel):
    friend_user_id: uuid.UUID
    username: str
    avatar_url: str | None
    rating: int
    friended_at: datetime


class VisibleAutomatonSummary(BaseModel):
    id: uuid.UUID
    name: str


class FriendProfileRead(BaseModel):
    user_id: uuid.UUID
    username: str
    avatar_url: str | None
    rating: int
    ranked_tournaments_played: int
    visible_automata: list[VisibleAutomatonSummary]


class FriendAutomatonCodeRead(BaseModel):
    code: str


class FriendSettingsRead(BaseModel):
    global_mode: GlobalMode
    automaton_ids: list[uuid.UUID]


class FriendSettingsUpdate(BaseModel):
    """Partial update - see FolderUpdate's docstring for the `exclude_unset=True`
    convention: an omitted `automaton_ids` means "leave the allow-list
    unchanged"; an explicit `[]` means "wholesale-replace with empty".
    """

    global_mode: GlobalMode | None = None
    automaton_ids: list[uuid.UUID] | None = None


class FriendVisibilityOverrideRead(BaseModel):
    friend_user_id: uuid.UUID
    mode: OverrideMode
    automaton_ids: list[uuid.UUID]


class FriendVisibilityOverrideUpdate(BaseModel):
    mode: OverrideMode | None = None
    automaton_ids: list[uuid.UUID] | None = None
