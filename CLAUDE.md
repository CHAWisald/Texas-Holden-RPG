# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working with the user

The user is smart but uninformed and sometimes may not know what he is talking about. You must understand user's prompt in a mindset of a project manager and then act accordingly based on your judgement.

## Running

```bash
npm --prefix frontend run build   # build the React UI (once, and after frontend changes)
fastapi dev main.py               # dev server — React UI at http://127.0.0.1:8000/, docs at /docs
npm --prefix frontend run dev     # frontend hot-reload on :5173 (calls the API on :8000)
python -m pytest -q               # test suite (191 tests, runs in <1 s)
python play.py                    # legacy CLI game (real terminal only — reads stdin)
```

Dependencies: `requirements.txt` (`fastapi`, `uvicorn`; `pytest` for tests) plus Node 20.19+ for the frontend build. The `game/` package itself is standard-library only.

**Frontends:** the React app in `frontend/` is the site. Its production build (`frontend/dist`) is mounted at `/` as the **last** route in `main.py` (a `/` mount swallows every unmatched path, so it must stay below all API routes; the mount is guarded by an existence check so the API runs before a first build). Its API base in `frontend/src/App.jsx` is `import.meta.env.DEV ? 'http://localhost:8000' : ''` — dev talks cross-origin to :8000 (the CORS middleware in `main.py` allowlists exactly the Vite origin :5173), the production build is same-origin. The legacy single-file vanilla UI `index.html` is served at `/classic` (`const API = ""`). `frontend/` was copied from the separate `poker-frontend` repo on 2026-07-03 — develop it here now. Production: `uvicorn main:app --host 0.0.0.0 --port $PORT`, **single worker only** (in-memory game store); `render.yaml` is the Render blueprint (Python deps + `npm ci`/`npm run build`).

## Architecture

A Texas Hold'em backend with two layered mechanics on top of standard poker: a **cheat-detection** mini-game (dealers may rig the shuffle; others may accuse) and **roles** (CURSED / GUNNER / LUCKY special abilities).

There are two parallel implementations:

1. **API path (current):** `main.py` (FastAPI) → `game/engine.py`. The engine is a pure state machine — no I/O, no classes; all game state is one JSON-serialisable dict. This is what the HTTP API and `tests/test_engine.py` exercise.
2. **Legacy CLI path:** `game/texas_holdem.py` + `game/player.py` + the `CheatSystem` / `RoleSystem` classes, which `print()` and read stdin directly. `play.py` launches it in a terminal (`main.py` no longer imports it), and `tests/test_roles.py` still covers `RoleSystem`. The engine deliberately re-implements this logic in pure form rather than calling it.

**API flow:** `POST /games` → `POST /games/{id}/start-hand` → (`/shuffle` → `/accuse` if the human is involved) → repeated `/action` → hand resolves → `/start-hand` again. `/ability` fires a role ability in any non-betting phase; during the player's betting turn, abilities ride the `/action` request via `use_ability_first` + `ability_target_id` instead (`apply_ability` rejects betting phases). Bots auto-advance server-side: every engine entry point runs bot turns until the next *human* decision point and returns the state paused there, with `state["phase"]` naming what input is expected and `state["events"]` listing what happened since the last call (cleared on each public engine call).

**Engine conventions (`game/engine.py`):**

- Phases: `WAITING → SHUFFLE_PHASE → ACCUSATION_PHASE → PREFLOP/FLOP/TURN/RIVER_BETTING → HAND_OVER → GAME_OVER`.
- Public API: `create_game`, `start_hand`, `apply_shuffle_decision`, `apply_accusation`, `apply_action`, `apply_ability`. Everything else is `_private`.
- Illegal client moves raise `IllegalMove` (subclass of `ValueError`), which `main.py` maps to HTTP 400; anything else surfaces as 500. Actions are validated *before* any state mutation so a rejected request never half-advances the game.
- Cards are `{"rank": int, "suit": str}` dicts inside the engine; `_c2d`/`_d2c` convert to/from the `Card` class only at `HandEvaluator` boundaries.
- Two event channels, both written by `_emit`: `state["events"]` is the machine-readable list (cleared at the top of every public engine call) and `state["log"]` is a human-readable per-hand story (reset only by `start_hand`, so it accumulates the whole hand). Log entries are `{"text": str, "private_to": pid|None}` — `private_to=None` for public lines; private lines (the dealer's own shuffle choice, devil/curse card tampering) carry the owner's id so the UI shows them only to that player. `_log_event` decides which event types produce a line; pure control-flow events (`dealt`, `street_start`, `accusation_prompt`, …) produce none.
- `main.py` keeps games in an in-memory dict and serialises each mutating endpoint on a per-game `threading.Lock` (FastAPI runs sync endpoints in a threadpool).

**Cheat mini-game:** the dealer secretly picks a cheat hand from `CHEAT_HANDS` (`game/cheat_system.py`) or shuffles honestly. The displayed shuffle time is drawn from overlapping distributions — honest is Beta(2,3) on 12–18 s (right-skewed); each cheat hand has its own clamped-Gaussian 3 s window inside 15–20 s, with stronger hands sitting higher (AA: 17–20 s). Accusing costs `2 × big_blind`; first accuser only. Caught cheating → dealer pays a penalty and the hand is re-dealt fairly; false accusation → accuser pays the dealer. If uncaught, the dealer's two chosen cards are reserved from the deck *before* anyone else is dealt.

**Roles** (definitions in `game/roles.py`, pure re-implementation in `engine.py`):

- **CURSED** — on bust, takes a devil loan (20 BB, repay 25 BB within 5–8 hands or be eliminated); while in devil state their hole cards may be tampered each hand. One-time ability: curse an opponent (tampered cards for 3–5 hands). Winning uncontested with a weak hand forgives 5 BB of debt.
- **GUNNER** — Russian-roulette revolver (one bullet, six chambers). Shooting an *opponent* costs `10 BB × 2^bullets_used` (bang kills them); self-shooting is **free** (click pays out 20 BB; bang eliminates the shooter) but still advances `bullets_used`, so each self-shot raises the price of the next opponent shot. Every trigger pull advances `bullets_used`. The revolver reloads **only** when an opponent is killed (`_reload_revolver` in the `shot_hit` path). The free self-shot and the forced bust-revival roulette in `_handle_bust` both pull the trigger at no chip cost. Insufficient chips block only opponent shots → `ability_failed` event, no state change.
- **LUCKY** — dealt 3 hole cards, keeps best 2; 30% immunity to curse/shot; 30% escape when caught cheating.

**React web UI (`frontend/` — the site):** Vite + React 19 + `motion`. `App.jsx` owns all state (`gameState`, `gameId`, `error`, `lastActions`) and one function per backend endpoint; children (`PlayerSeat`, `ActionBar`, `EventLog`, `AnnounceBanner`, `ShootFlash`, `Card`) receive state and those functions as props. It mirrors the classic UI's patterns: 2 s polling via `useEffect` (skips identical payloads by JSON comparison), event-batch fingerprinting for per-seat action labels (`applyEventLabels`), and `activePlayerId(state)` as the single source for whose turn it is.

**Classic web UI (`index.html`, served at `/classic` — legacy reference):** one self-contained file — CSS, markup, and vanilla JS, no dependencies. Feature-complete; useful as the reference when porting behaviour to React.

- All rendering funnels through `showState(state)`: it caches the response in `lastState`, dumps raw JSON into the debug `<details>` block, then calls `processEvents`, `renderTable` (phase label, community cards, pot, shuffle time), `renderSeats`, `renderLog`, `updateControls`, and finally `updatePolling`. New display features should hang off this funnel, not off individual button handlers — poll re-renders must be idempotent.
- **Polling:** the page polls `GET /games/{game_id}` every 2 s (`POLL_MS`) and feeds the result to `showState`. `updatePolling()` starts the timer when a game is active and stops it when there is none or the phase is GAME_OVER; `pollInFlight` guards against overlapping requests.
- **Event de-dup:** mutating engine calls clear `state.events`, but GET polls re-deliver the same list, so `processEvents` fingerprints it (`lastEventsKey = JSON.stringify(events)`) and skips repeats. Events drive two things: per-seat action labels (`lastActions[player_id]` — "fold", "call 50", "raise to 200", shot/curse outcomes; cleared on each street start) and the `#announce` banner queue (`queueAnnouncement` — accusation suspense, cheat verdicts).
- **Game log panel:** `renderLog(state)` rebuilds `#log-list` from `state.log`, showing public lines plus only the human's own private ones (rendered gold with a 🔒 prefix; other players' `private_to` lines are dropped). Like `processEvents`, it fingerprints the log (`lastLogKey`) so 2 s polls don't rebuild the list and fight the user's scroll; on a real change it re-renders and scrolls to the newest line.
- `activePlayerId(state)` is the single source for "who must act": `hand_active_ids[dealer_pos]` in SHUFFLE_PHASE, `accusation_order[0]` in ACCUSATION_PHASE, `to_act[0]` in `*_BETTING`, else null. Both the turn highlight (`.seat.active`) and control gating use it; the button handlers read the same fields when building request bodies.
- `updateControls()` re-gates everything from `lastState` after each response: Start Hand is visible only in WAITING/HAND_OVER; the betting group `#bet-controls` is shown only in a `*_BETTING` phase when the actor `is_human` (with `#bet-status` showing "bet is X — Y to call", Check disabled when facing a bet, Call labelled with the amount); shuffle/accuse buttons enable in their phases. Use the `.hidden` class (`display: none !important`) to hide elements — the bare `hidden` attribute loses to `.control-group { display: flex }`.
- **Ability UI:** `#ability-controls` shows whenever the human's role grants an ability (Gunner's button displays the live shot price). Between hands the button POSTs `/ability` directly. During the human's betting turn it instead *arms* the ability (`abilityArmed` flag); the next bet/check/call/raise/fold sends `use_ability_first: true` + `ability_target_id` on the `/action` request. The target `<select>` is rebuilt every render with the previous selection preserved (polling would otherwise reset it).
- All requests go through the `api()` helper (network errors and non-2xx → thrown `Error`, rendered into `#error`). Every handler ends by calling `showState` with the returned state — the server response is the only thing that updates the UI.
- Seats are placed on an ellipse with percentage `left`/`top` (seat 0 bottom-centre, clockwise; bottom-arc seats dip an extra 5% so the human's seat clears the pot). Each seat shows dealer button, position tag (`positionNames(n)` — BTN/SB/BB/UTG/…/CO, heads-up BTN/SB vs BB), role tag, current `street_bet` chip, and last-action label. Cards are CSS boxes built by `cardEl()` from the engine's `{rank, suit}` dicts.
- **Hole-card reveal:** only the human's cards render during play. At showdown, a seat's cards are revealed iff its player id is in `hand_result.all_hands` (i.e. they were still in the hand) — folded players stay hidden. Note the server still *sends* all `hole_cards`; hiding them properly would need a backend change.
- **New Game defaults:** 4 players × 1000 chips, blinds 25/50 (20 BB stacks). The human picks a role from `#role-select` (or none); bots are assigned random roles.

**Module map:**

| File | Responsibility |
|---|---|
| `main.py` | FastAPI app: endpoints, Pydantic request models, per-game locks, `IllegalMove` → 400, serves both UIs |
| `frontend/` | React web UI (Vite) — built to `frontend/dist`, mounted at `/` |
| `index.html` | Legacy single-file vanilla-JS UI, served at `/classic` (see Classic web UI section) |
| `game/engine.py` | Pure state-machine engine — the source of truth for game logic |
| `game/card.py` | `Card` (rank 2–14, `Suit` enum), `Deck` |
| `game/hand_evaluator.py` | `HandEvaluator.best_hand()` — scores any 5-of-N subset; returns `(score_tuple, hand_name)`, or `None` for <5 cards |
| `game/cheat_system.py` | Shared constants (`CHEAT_HANDS`, `HONEST_RANGE`, …) + legacy `CheatSystem` class and `timed_input()` |
| `game/roles.py` | `RoleType` enum, role descriptions, legacy `RoleSystem` class |
| `game/texas_holdem.py`, `game/player.py` | Legacy CLI game loop and player classes (unused by the API) |
| `play.py` | Terminal launcher for the legacy CLI (human as GUNNER vs 3 bots) |
| `tests/` | pytest: `test_engine.py` (engine API), `test_hand_evaluator.py`, `test_roles.py` (legacy RoleSystem) |

## Key design decisions

- Engine state must stay JSON-serialisable (it's returned verbatim as the API response) — no class instances in the dict.
- Logic changes generally need to land in `engine.py`; the class-based versions in `roles.py`/`cheat_system.py`/`texas_holdem.py` are the legacy CLI counterparts, not callees.
- Ace rank is stored as 14; `HandEvaluator._check_straight` handles the ace-low wheel (A-2-3-4-5) by remapping to `[5,4,3,2,1]`.
- Per-player `street_bet` tracks chips committed this street (reset by `_reset_street()`); `total_bet` tracks the whole hand and drives side-pot layering in `_distribute_side_pots` (uncalled over-bets are refunded).
- On a raise, `to_act` is rebuilt from `street_player_order` excluding the raiser; min-raise is always 1 BB.
- Bust revival (`_handle_bust`) only runs for players in `hand_active_ids`, so a player eliminated in an earlier hand can't be re-revived.
- Dealer rotation uses `dealer_idx` modulo the alive-players list, recalculated each hand so eliminated players are skipped.
