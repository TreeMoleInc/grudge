// Hand-written TS mirrors of backend/src/grudge_backend/schemas/*.py and the
// relevant router response models. Kept in sync by hand for now - codegen from
// FastAPI's /openapi.json is a cheap future upgrade once the API stabilizes,
// not needed to start (see the Phase 4 plan).

export type UUID = string;
export type ISODateTime = string;

export interface UserRead {
  id: UUID;
  username: string;
  avatar_url: string | null;
  rating: number;
  ranked_tournaments_played: number;
  created_at: ISODateTime;
}

export interface FolderRead {
  id: UUID;
  user_id: UUID;
  parent_id: UUID | null;
  name: string;
  sort_order: number;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface FolderCreate {
  name: string;
  parent_id?: UUID | null;
}

export interface FolderUpdate {
  name?: string;
  parent_id?: UUID | null;
}

export interface AutomatonRead {
  id: UUID;
  user_id: UUID;
  folder_id: UUID | null;
  name: string;
  sort_order: number;
  active_version_id: UUID | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface AutomatonCreate {
  name: string;
  folder_id?: UUID | null;
  code?: string | null;
  share_with_friends?: boolean;
}

export interface AutomatonUpdate {
  name?: string;
  folder_id?: UUID | null;
}

export interface VersionSummary {
  id: UUID;
  automaton_id: UUID;
  name: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface VersionRead extends VersionSummary {
  code: string;
}

export interface AutomatonCreateResponse extends AutomatonRead {
  first_version: VersionRead;
}

export interface VersionCreate {
  name?: string | null;
  code?: string | null;
}

export interface VersionUpdate {
  name?: string;
  code?: string;
}

// -- Matchmaking --------------------------------------------------------

export type QueueType = "ranked" | "unranked";

export interface JoinQueueResponse {
  entry_id: UUID;
  room_id: UUID;
  joined_at: ISODateTime;
  tournament_id: UUID | null;
  member_count: number;
  capacity: number;
}

// -- Sim rooms ------------------------------------------------------------

export interface SimRoomRead {
  id: UUID;
  owner_user_id: UUID;
  invite_code: string;
  status: "open" | "started";
}

export interface SimRoomEntryRead {
  id: UUID;
  sim_room_id: UUID;
  user_id: UUID;
  automaton_id: UUID;
  automaton_name: string;
  owner_username: string;
}

export interface SimRoomWithEntriesRead extends SimRoomRead {
  entries: SimRoomEntryRead[];
}

export interface StartSimRoomResponse {
  tournament_id: UUID;
}

export interface LeaveSimRoomResponse {
  room_closed: boolean;
  new_owner_user_id: UUID | null;
}

export interface SimRoomInviteRead {
  id: UUID;
  sim_room_id: UUID;
  invite_code: string;
  owner_username: string;
  invited_at: ISODateTime;
}

// -- Tournaments ------------------------------------------------------------

export type TournamentType = "ranked" | "unranked" | "sim";
export type TournamentStatus = "pending" | "running" | "completed" | "failed_voided";

export interface TournamentEntrant {
  user_id: UUID;
  automaton_id: UUID;
  automaton_version_id: UUID | null;
  automaton_name: string | null;
  automaton_version_name: string | null;
  owner_username: string | null;
  rating_snapshot: number;
  code_snapshot: string | null;
  // Only set for ranked tournaments and a non-faulted entrant - null for
  // unranked/sim (never touch rating) and for a faulted automaton (excluded
  // from the rating update entirely).
  rating_delta: number | null;
}

export interface RoundLogEntry {
  round_index: number;
  move_a: "COOPERATE" | "DEFECT";
  move_b: "COOPERATE" | "DEFECT";
  points_a: number;
  points_b: number;
}

export interface MatchResultData {
  automaton_a_id: string;
  automaton_b_id: string;
  games_played: number;
  score_a: number;
  score_b: number;
  status: "completed" | "voided";
  voided_side: "a" | "b" | "both" | null;
  void_reason: string | null;
  rounds: RoundLogEntry[];
}

export interface StandingEntryData {
  automaton_id: string;
  total_points: number;
  total_games: number;
  points_per_game: number;
}

export interface FaultedEntryData {
  automaton_id: string;
  reason: string;
  voided_match_ids: [string, string][];
}

export interface TournamentResultData {
  automaton_ids: string[];
  matches: MatchResultData[];
  standings: StandingEntryData[];
  faulted: FaultedEntryData[];
}

export interface TournamentRead {
  id: UUID;
  type: TournamentType;
  status: TournamentStatus;
  entrants: TournamentEntrant[];
  result: TournamentResultData | null;
  error_message: string | null;
}

export interface MyTournamentEntryRead {
  tournament_id: UUID;
  tournament_type: TournamentType;
  status: TournamentStatus;
  created_at: ISODateTime;
  automaton_id: UUID;
  automaton_name: string | null;
  automaton_version_id: UUID | null;
  automaton_version_name: string | null;
  placement: number | null;
  voided: boolean;
}

// -- Match history / stats ---------------------------------------------------

export interface AutomatonRecordRead {
  automaton_id: UUID;
  matches_played: number;
  wins: number;
  losses: number;
  ties: number;
  voided_matches: number;
  average_points_per_game: number;
}

export interface OpponentSummaryRead {
  opponent_automaton_id: UUID;
  opponent_name: string | null;
  opponent_owner_username: string | null;
  matches_played: number;
  wins: number;
  losses: number;
  ties: number;
  voided_matches: number;
}

export interface MatchSummaryRead {
  id: UUID;
  tournament_id: UUID;
  automaton_a_id: UUID | null;
  automaton_b_id: UUID | null;
  games_played: number;
  score_a: number;
  score_b: number;
  status: string;
  void_reason: string | null;
  created_at: ISODateTime;
}

export interface HeadToHeadRead {
  opponent_automaton_id: UUID;
  opponent_name: string | null;
  opponent_owner_username: string | null;
  wins: number;
  losses: number;
  ties: number;
  voided_matches: number;
  matches: MatchSummaryRead[];
}

// -- Friends & visibility ---------------------------------------------------

export interface FriendRequestCreate {
  username: string;
}

export interface FriendRequestRead {
  id: UUID;
  from_user_id: UUID;
  from_username: string;
  to_user_id: UUID;
  to_username: string;
  created_at: ISODateTime;
}

export interface FriendRead {
  friend_user_id: UUID;
  username: string;
  avatar_url: string | null;
  rating: number;
  friended_at: ISODateTime;
}

export interface VisibleAutomatonSummary {
  id: UUID;
  name: string;
}

export interface FriendProfileRead {
  user_id: UUID;
  username: string;
  avatar_url: string | null;
  rating: number;
  ranked_tournaments_played: number;
  visible_automata: VisibleAutomatonSummary[];
}

export interface FriendAutomatonCodeRead {
  code: string;
}

export type GlobalVisibilityMode = "show" | "hide" | "specific";
export type OverrideVisibilityMode = "default" | "show" | "hide" | "specific";

export interface FriendSettingsRead {
  global_mode: GlobalVisibilityMode;
  automaton_ids: UUID[];
}

export interface FriendSettingsUpdate {
  global_mode?: GlobalVisibilityMode;
  automaton_ids?: UUID[];
}

export interface FriendVisibilityOverrideRead {
  friend_user_id: UUID;
  mode: OverrideVisibilityMode;
  automaton_ids: UUID[];
}

export interface FriendVisibilityOverrideUpdate {
  mode?: OverrideVisibilityMode;
  automaton_ids?: UUID[];
}

// -- Stats ----------------------------------------------------------------

export interface LiveStatsRead {
  online_count: number;
  in_activity_count: number;
}

// -- Notifications ----------------------------------------------------------

export interface NotificationRead {
  id: UUID;
  type: string;
  tournament_id: UUID | null;
  automaton_id: UUID | null;
  automaton_name: string | null;
  reason: string;
  read_at: ISODateTime | null;
  created_at: ISODateTime;
}
