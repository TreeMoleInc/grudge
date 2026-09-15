from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    tournament_id: uuid.UUID | None
    automaton_id: uuid.UUID | None
    automaton_name: str | None
    reason: str
    read_at: datetime | None
    created_at: datetime
