from __future__ import annotations

from pydantic import BaseModel


class LiveStatsRead(BaseModel):
    online_count: int
    in_activity_count: int
