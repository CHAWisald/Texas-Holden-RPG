"""
main.py — FastAPI entry point for Texas Hold'em.

Run with:  fastapi dev main.py
Docs at:   http://127.0.0.1:8000/docs
"""

import threading
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from game.engine import (
    create_game,
    start_hand,
    apply_shuffle_decision,
    apply_accusation,
    apply_action,
    apply_ability,
    IllegalMove,
)
from game.cheat_system import CHEAT_HAND_OPTIONS, CHEAT_HANDS

app = FastAPI(
    title="Texas Hold'em API",
    description=(
        "State-machine poker backend. "
        "Create a game, call /start-hand, then drive play with "
        "/shuffle → /accuse → /action. Bots auto-advance server-side."
    ),
)
# The web UI is served same-origin at "/" and needs no CORS. This exists only
# so the React dev server (poker-frontend, Vite on :5173) can call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Web UI ─────────────────────────────────────────────────────────────────────
# The React app (frontend/) is the site: its production build is mounted at "/"
# at the BOTTOM of this file, after every API route, so the mount only catches
# paths no endpoint claimed. The old single-file vanilla UI stays reachable at
# /classic.

_CLASSIC_HTML = Path(__file__).parent / "index.html"
_FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"


@app.get("/classic", include_in_schema=False)
def classic_ui():
    return FileResponse(_CLASSIC_HTML)
# ── In-memory store ────────────────────────────────────────────────────────────
# Maps game_id (str) → game state (dict).
games: dict[str, dict] = {}

# Per-game locks. FastAPI runs these sync endpoints in a threadpool, so two
# requests for the same game could otherwise interleave their in-place mutations
# of the shared state dict. Each mutating endpoint serialises on the game's lock.
_locks_guard: threading.Lock = threading.Lock()
_game_locks: dict[str, threading.Lock] = {}


def _lock_for(game_id: str) -> threading.Lock:
    with _locks_guard:
        return _game_locks.setdefault(game_id, threading.Lock())


# ── Request models ─────────────────────────────────────────────────────────────

class PlayerConfig(BaseModel):
    id: str
    name: str
    is_human: bool
    chips: int = 1000
    aggression: float = 0.5      # ignored for human players
    role: Optional[str] = None   # "CURSED" | "GUNNER" | "LUCKY" | null


class CreateGameRequest(BaseModel):
    players: list[PlayerConfig]
    small_blind: int = 10
    big_blind: int = 20


class ShuffleRequest(BaseModel):
    dealer_id: str
    cheated: bool
    chosen_hand: Optional[str] = None   # required when cheated=true; see GET /cheat-hands


class AccusationRequest(BaseModel):
    player_id: str
    accuses: bool


class ActionRequest(BaseModel):
    player_id: str
    action: str                          # "fold" | "check" | "call" | "raise" | "all-in"
    amount: int = 0                      # chips to raise by (above the call amount)
    use_ability_first: bool = False
    ability_target_id: Optional[str] = None   # target for shoot/curse when use_ability_first


class AbilityRequest(BaseModel):
    player_id: str
    ability_type: str               # "shoot" | "curse"
    target_id: Optional[str] = None


# ── Helper ─────────────────────────────────────────────────────────────────────

def _get_or_404(game_id: str) -> dict:
    if game_id not in games:
        raise HTTPException(status_code=404, detail=f"Game {game_id!r} not found")
    return games[game_id]


# ── Reference endpoint ─────────────────────────────────────────────────────────

@app.get("/cheat-hands", summary="List all cheat-hand options for the shuffle phase")
def list_cheat_hands():
    """Returns the available cheat hands and their shuffle-time ranges."""
    return {
        k: {"label": v.label, "lo": v.lo, "hi": v.hi, "mean": v.mean}
        for k, v in CHEAT_HANDS.items()
    }


# ── Game lifecycle ─────────────────────────────────────────────────────────────

@app.post("/games", summary="Create a new game")
def new_game(req: CreateGameRequest):
    """
    Create a game with the given players.
    Returns the initial state (phase = WAITING).
    Call /games/{id}/start-hand to begin the first hand.
    """
    game_id = str(uuid.uuid4())
    state = create_game(
        players_config=[p.model_dump() for p in req.players],
        small_blind=req.small_blind,
        big_blind=req.big_blind,
    )
    state["game_id"] = game_id
    games[game_id] = state
    return state


@app.get("/games/{game_id}", summary="Get current game state")
def get_game(game_id: str):
    return _get_or_404(game_id)


@app.post("/games/{game_id}/start-hand", summary="Start the next hand")
def do_start_hand(game_id: str):
    """
    Valid in WAITING or HAND_OVER.
    Returns state at the next human decision point:
    SHUFFLE_PHASE, ACCUSATION_PHASE, a *_BETTING phase,
    or HAND_OVER / GAME_OVER if the hand resolved immediately.
    """
    with _lock_for(game_id):
        state = _get_or_404(game_id)
        try:
            games[game_id] = start_hand(state)
        except IllegalMove as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return games[game_id]


# ── Cheat / accusation phase ───────────────────────────────────────────────────

@app.post("/games/{game_id}/shuffle", summary="Dealer commits shuffle decision")
def do_shuffle(game_id: str, req: ShuffleRequest):
    """
    Valid in SHUFFLE_PHASE only (human dealer).
    Set cheated=false for an honest shuffle; cheated=true requires chosen_hand
    from GET /cheat-hands.
    Server generates the shuffle time, then auto-processes bot accusations.
    Returns state at ACCUSATION_PHASE (if a human needs to decide) or
    directly at PREFLOP_BETTING.
    """
    with _lock_for(game_id):
        state = _get_or_404(game_id)
        try:
            games[game_id] = apply_shuffle_decision(
                state, req.dealer_id, req.cheated, req.chosen_hand
            )
        except IllegalMove as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return games[game_id]


@app.post("/games/{game_id}/accuse", summary="Player decides whether to accuse the dealer")
def do_accuse(game_id: str, req: AccusationRequest):
    """
    Valid in ACCUSATION_PHASE only.
    The player_id must be the current head of accusation_order.
    Costs 2×BB if accuses=true and the dealer is honest (false accusation).
    After all humans have decided, resolution and dealing happen automatically.
    """
    with _lock_for(game_id):
        state = _get_or_404(game_id)
        try:
            games[game_id] = apply_accusation(state, req.player_id, req.accuses)
        except IllegalMove as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return games[game_id]


# ── Betting ────────────────────────────────────────────────────────────────────

@app.post("/games/{game_id}/action", summary="Submit a betting action")
def do_action(game_id: str, req: ActionRequest):
    """
    Valid in PREFLOP_BETTING, FLOP_BETTING, TURN_BETTING, or RIVER_BETTING.
    player_id must be to_act[0].

    Actions:
    - fold    — surrender the hand
    - check   — pass (only valid when to_call == 0)
    - call    — match the current bet
    - raise   — raise by `amount` chips above the call amount
    - all-in  — put in all remaining chips

    Set use_ability_first=true to fire the role ability before betting.
    Provide ability_target_id to name a shoot/curse target (omit for auto-pick).
    Bots auto-advance after this action until the next human turn or phase end.
    """
    with _lock_for(game_id):
        state = _get_or_404(game_id)
        try:
            games[game_id] = apply_action(
                state,
                req.player_id,
                req.action,
                req.amount,
                req.use_ability_first,
                req.ability_target_id,
            )
        except IllegalMove as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return games[game_id]


# ── Role abilities (between hands) ────────────────────────────────────────────

@app.post("/games/{game_id}/ability", summary="Use a role ability outside of betting")
def do_ability(game_id: str, req: AbilityRequest):
    """
    For Gunner: ability_type="shoot", target_id=opponent's player id (or null to self-shoot).
    For Cursed: ability_type="curse", target_id=opponent's player id (or null to auto-pick).
    Valid in any non-betting phase (typically HAND_OVER for between-hand use).
    During betting, pass use_ability_first=true on /action instead.
    """
    with _lock_for(game_id):
        state = _get_or_404(game_id)
        try:
            games[game_id] = apply_ability(
                state, req.player_id, req.ability_type, req.target_id
            )
        except IllegalMove as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return games[game_id]


# ── React app mount ────────────────────────────────────────────────────────────
# Must stay the LAST route: a mount at "/" swallows every path not matched by
# an endpoint above. Guarded so the API still runs before `npm run build`
# (dev flow: Vite serves the app on :5173 instead).

if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")

