from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AutomatonRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    automaton_id: uuid.UUID
    matches_played: int
    wins: int
    losses: int
    ties: int
    voided_matches: int
    average_points_per_game: float


class MatchSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tournament_id: uuid.UUID
    automaton_a_id: uuid.UUID | None
    automaton_b_id: uuid.UUID | None
    games_played: int
    score_a: int
    score_b: int
    status: str
    void_reason: str | None
    created_at: datetime


class HeadToHeadRead(BaseModel):
    opponent_automaton_id: uuid.UUID
    opponent_name: str | None
    opponent_owner_username: str | None
    wins: int
    losses: int
    ties: int
    voided_matches: int
    matches: list[MatchSummaryRead]


class OpponentSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    opponent_automaton_id: uuid.UUID
    opponent_name: str | None
    opponent_owner_username: str | None
    matches_played: int
    wins: int
    losses: int
    ties: int
    voided_matches: int
