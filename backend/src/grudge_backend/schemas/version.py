from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_VERSION_CODE = "def decide(history):\n    return COOPERATE\n"


class VersionCreate(BaseModel):
    """Explicit new-version action, per the mutable-save-slot design. If `code`
    is omitted, the service layer forks the automaton's current active version's
    code as a starting point rather than defaulting to blank.
    """

    name: str | None = Field(default=None, max_length=255)
    code: str | None = None


class VersionUpdate(BaseModel):
    """In-place edit/autosave - never creates a new row. See FolderUpdate's
    docstring for the `exclude_unset=True` partial-update convention.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = None


class VersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    automaton_id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime


class VersionRead(VersionSummary):
    code: str
