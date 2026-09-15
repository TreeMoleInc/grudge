from __future__ import annotations

from pydantic import BaseModel


class ProviderUserInfo(BaseModel):
    """Normalized shape fetch_google_user() returns - kept as its own type
    (rather than inlining Google's fields directly) so a future provider can
    return the same shape without callers caring which provider it came from.
    """

    provider: str
    provider_user_id: str
    email: str | None
    username: str
    avatar_url: str | None
