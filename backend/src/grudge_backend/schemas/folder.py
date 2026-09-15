from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None


class FolderUpdate(BaseModel):
    """Partial update - callers should read with `exclude_unset=True` so an
    omitted field means "leave unchanged" while an explicit `null` for
    `parent_id` means "move to root", not "no change".
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None


class FolderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    sort_order: int
    created_at: datetime
    updated_at: datetime
