from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 3-20 characters: letters, digits, underscore, hyphen. Enforced here (schema
# level, a 422 with no DB round trip for obviously-malformed input) as well
# as at the DB level via the case-insensitive uniqueness index (migration
# 0011) - format isn't something a unique index can check, so both layers
# are needed, same "validate cheaply first, then hit the DB" shape as the
# rest of this app's request validation.
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,20}$")


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    username_is_default: bool
    avatar_url: str | None
    rating: int
    ranked_tournaments_played: int
    created_at: datetime


class UsernameUpdate(BaseModel):
    username: str = Field(min_length=3, max_length=20)

    @field_validator("username")
    @classmethod
    def _validate_format(cls, value: str) -> str:
        if not USERNAME_PATTERN.fullmatch(value):
            raise ValueError(
                "Usernames must be 3-20 characters: letters, numbers, underscores, or hyphens only."
            )
        return value
