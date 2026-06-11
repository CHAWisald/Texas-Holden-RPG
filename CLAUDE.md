# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running

```bash
fastapi dev main.py        # API server — interactive docs at http://127.0.0.1:8000/docs
python -m pytest -q        # test suite (186 tests, runs in <1 s)
```

Dependencies: `fastapi`, `pydantic`, `pytest`. The `game/` package itself is standard-library only. `index.html` is a minimal dev console (open directly in a browser; it talks to `localhost:8000`).

## Architecture

A Texas Hold'em backend with two layered mechanics on top of standard poker: a **cheat-detection** mini-game (dealers may rig the shuffle; others may accuse) and **roles** (CURSED / GUNNER / LUCKY special abilities).

There are two parallel implementations:

1. **API path (current):** `main.py` (FastAPI) → `game/engine.py`. The engine is a pure state machine — no I/O, no classes; all game state is one JSON-serialisable dict. This is what the HTTP API and `tests/test_engine.py` exercise.
2. **Legacy CLI path:** `game/texas_holdem.py` + `game/player.py` + the `CheatSystem` / `RoleSystem` classes, which `print()` and read stdin directly. Nothing launches it anymore (`main.py` no longer imports it), but `tests/test_roles.py` still covers `RoleSystem`. The engine deliberately re-implements this logic in pure form rather than calling it.

**API flow:** `POST /games` → `POST /games/{id}/start-hand` → (`/shuffle` → `/accuse` if the human is involved) → repeated `/action` → hand resolves → `/start-hand` again. `/ability` fires a role ability between hands. Bots auto-advance server-side: every engine entry point runs bot turns until the next *human* decision point and returns the state paused there, with `state["phase"]` naming what input is expected and `state["events"]` listing what happened since the last call (cleared on each public engine call).

**Engine conventions (`game/engine.py`):**

- Phases: `WAITING → SHUFFLE_PHASE → ACCUSATION_PHASE → PREFLOP/FLOP/TURN/RIVER_BETTING → HAND_OVER → GAME_OVER`.
- Public API: `create_game`, `start_hand`, `apply_shuffle_decision`, `apply_accusation`, `apply_action`, `apply_ability`. Everything else is `_private`.
- Illegal client moves raise `IllegalMove` (subclass of `ValueError`), which `main.py` maps to HTTP 400; anything else surfaces as 500. Actions are validated *before* any state mutation so a rejected request never half-advances the game.
- Cards are `{"rank": int, "suit": str}` dicts inside the engine; `_c2d`/`_d2c` convert to/from the `Card` class only at `HandEvaluator` boundaries.
- `main.py` keeps games in an in-memory dict and serialises each mutating endpoint on a per-game `threading.Lock` (FastAPI runs sync endpoints in a threadpool).

**Cheat mini-game:** the dealer secretly picks a cheat hand from `CHEAT_HANDS` (`game/cheat_system.py`) or shuffles honestly. The displayed shuffle time is drawn from overlapping distributions — honest is Beta(2,3) on 12–18 s (right-skewed); each cheat hand has its own clamped-Gaussian 3 s window inside 15–20 s, with stronger hands sitting higher (AA: 17–20 s). Accusing costs `2 × big_blind`; first accuser only. Caught cheating → dealer pays a penalty and the hand is re-dealt fairly; false accusation → accuser pays the dealer. If uncaught, the dealer's two chosen cards are reserved from the deck *before* anyone else is dealt.

**Roles** (definitions in `game/roles.py`, pure re-implementation in `engine.py`):

- **CURSED** — on bust, takes a devil loan (20 BB, repay 25 BB within 5–8 hands or be eliminated); while in devil state their hole cards may be tampered each hand. One-time ability: curse an opponent (tampered cards for 3–5 hands). Winning uncontested with a weak hand forgives 5 BB of debt.
- **GUNNER** — Russian-roulette revolver. On bust, may self-shoot for 20 BB (or die). Can pay chips (10 BB, doubling per shot) to shoot an opponent dead.
- **LUCKY** — dealt 3 hole cards, keeps best 2; 30% immunity to curse/shot; 30% escape when caught cheating.

**Module map:**

| File | Responsibility |
|---|---|
| `main.py` | FastAPI app: endpoints, Pydantic request models, per-game locks, `IllegalMove` → 400 |
| `game/engine.py` | Pure state-machine engine — the source of truth for game logic |
| `game/card.py` | `Card` (rank 2–14, `Suit` enum), `Deck` |
| `game/hand_evaluator.py` | `HandEvaluator.best_hand()` — scores any 5-of-N subset; returns `(score_tuple, hand_name)`, or `None` for <5 cards |
| `game/cheat_system.py` | Shared constants (`CHEAT_HANDS`, `HONEST_RANGE`, …) + legacy `CheatSystem` class and `timed_input()` |
| `game/roles.py` | `RoleType` enum, role descriptions, legacy `RoleSystem` class |
| `game/texas_holdem.py`, `game/player.py` | Legacy CLI game loop and player classes (unused by the API) |
| `tests/` | pytest: `test_engine.py` (engine API), `test_hand_evaluator.py`, `test_roles.py` (legacy RoleSystem) |

## Key design decisions

- Engine state must stay JSON-serialisable (it's returned verbatim as the API response) — no class instances in the dict.
- Logic changes generally need to land in `engine.py`; the class-based versions in `roles.py`/`cheat_system.py`/`texas_holdem.py` are the legacy CLI counterparts, not callees.
- Ace rank is stored as 14; `HandEvaluator._check_straight` handles the ace-low wheel (A-2-3-4-5) by remapping to `[5,4,3,2,1]`.
- Per-player `street_bet` tracks chips committed this street (reset by `_reset_street()`); `total_bet` tracks the whole hand and drives side-pot layering in `_distribute_side_pots` (uncalled over-bets are refunded).
- On a raise, `to_act` is rebuilt from `street_player_order` excluding the raiser; min-raise is always 1 BB.
- Bust revival (`_handle_bust`) only runs for players in `hand_active_ids`, so a player eliminated in an earlier hand can't be re-revived.
- Dealer rotation uses `dealer_idx` modulo the alive-players list, recalculated each hand so eliminated players are skipped.
