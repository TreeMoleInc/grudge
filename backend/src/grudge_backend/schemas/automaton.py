from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from grudge_backend.schemas.version import VersionRead


class AutomatonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    folder_id: uuid.UUID | None = None
    code: str | None = None  # initial code for the first version; blank default if omitted
    # CLAUDE.md S2: new automata default to excluded from any "specific"
    # allow-list - this opts the new automaton into the global allow-list
    # (and every existing per-friend override currently in "specific" mode)
    # at creation time instead of forcing a separate trip to Settings.
    share_with_friends: bool = False


class AutomatonUpdate(BaseModel):
    """See FolderUpdate's docstring for the `exclude_unset=True` partial-update
    convention this relies on.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    folder_id: uuid.UUID | None = None


class AutomatonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    folder_id: uuid.UUID | None
    name: str
    sort_order: int
    active_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class AutomatonCreateResponse(AutomatonRead):
    """POST /automata returns the automaton plus its freshly-created first
    version, so the client doesn't need a second round trip to start editing.
    """

    first_version: VersionRead


class SetActiveVersion(BaseModel):
    version_id: uuid.UUID
