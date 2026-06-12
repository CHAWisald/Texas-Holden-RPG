# Texas Hold'em RPG

A Texas Hold'em poker engine with two RPG-style mechanics layered on top of standard play:

- **Cheat mini-game** — the dealer may secretly rig the shuffle; other players can pay to accuse them. Get it right and the cheat is punished; get it wrong and you pay the dealer.
- **Roles** — each player can hold a special ability:
  - **CURSED** — on bust, takes a devil loan instead of dying (repay it in time or be eliminated); can curse an opponent's hole cards once.
  - **GUNNER** — a one-bullet, six-chamber revolver. Pay an escalating price to shoot an opponent dead, or gamble on a self-shoot for a chip payout — at the risk of eliminating yourself.
  - **LUCKY** — dealt 3 hole cards and keeps the best 2; partial immunity to curses, shots, and getting caught cheating.

The game is served as an HTTP API with a single-file web UI that renders the table as a casino felt and polls for live updates.

## Requirements

- Python 3.10+
- `fastapi`, `pydantic`, `pytest`

```bash
pip install fastapi pydantic pytest
```

The `game/` package itself is standard-library only — the dependencies are just for the API server and tests.

## Running

Start the API server:

```bash
fastapi dev main.py
```

- Interactive API docs: http://127.0.0.1:8000/docs
- Web UI: open `index.html` directly in a browser while the server runs on `localhost:8000` (no build step, no framework).

Run the test suite:

```bash
python -m pytest -q
```

## How a hand flows

```
POST /games                       create a game
POST /games/{id}/start-hand       deal a hand
  POST /games/{id}/shuffle        dealer's shuffle decision (cheat or honest)
  POST /games/{id}/accuse         optional: accuse the dealer of cheating
POST /games/{id}/action           bet / call / raise / check / fold (repeat)
POST /games/{id}/ability          fire a role ability (between hands)
GET  /games/{id}                  poll current state
```

Bots advance automatically server-side: every call runs the bots until the next decision the human must make, then returns the state paused there. The response includes the current `phase` (what input is expected) and an `events` list describing what just happened.

## Project layout

| Path | Responsibility |
|---|---|
| `main.py` | FastAPI app — endpoints, request models, per-game locks |
| `index.html` | Single-file web UI: visual table + state-gated action bar |
| `game/engine.py` | Pure state-machine engine — the source of truth for game logic |
| `game/card.py` | `Card`, `Suit`, `Deck` |
| `game/hand_evaluator.py` | `HandEvaluator.best_hand()` — scores the best 5 of N cards |
| `game/cheat_system.py` | Cheat-hand constants and shuffle-timing distributions |
| `game/roles.py` | Role definitions and descriptions |
| `tests/` | pytest suite (188 tests) |

The engine is a pure state machine: no I/O and no classes, with all game state held in one JSON-serialisable dict that is returned verbatim as the API response. See [CLAUDE.md](CLAUDE.md) for the full architecture notes.

## Status

Work in progress. The FastAPI engine and web UI are the active implementation; the older standard-library CLI modules (`game/texas_holdem.py`, `game/player.py`) are legacy and no longer launched.
