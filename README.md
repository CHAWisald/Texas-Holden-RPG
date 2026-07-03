# Texas Hold'em RPG

A Texas Hold'em poker engine with two RPG-style mechanics layered on top of standard play:

- **Cheat mini-game** — the dealer may secretly rig the shuffle; other players can pay to accuse them. Get it right and the cheat is punished; get it wrong and you pay the dealer.
- **Roles** — each player can hold a special ability:
  - **CURSED** — on bust, takes a devil loan instead of dying (repay it in time or be eliminated); can curse an opponent's hole cards once.
  - **GUNNER** — a one-bullet, six-chamber revolver. Pay an escalating price to shoot an opponent dead, or gamble on a self-shoot for a chip payout — at the risk of eliminating yourself.
  - **LUCKY** — dealt 3 hole cards and keeps the best 2; partial immunity to curses, shots, and getting caught cheating.

The game is served as an HTTP API with a React web UI (`frontend/`) that renders the table as a casino felt and polls for live updates. An older single-file vanilla-JS UI (`index.html`) is kept reachable at `/classic`.

## Requirements

- Python 3.10+
- Node.js 20.19+ (for building the React frontend)

```bash
pip install -r requirements.txt
npm --prefix frontend ci
```

The `game/` package itself is standard-library only — the dependencies are just for the API server, the frontend build, and tests.

## Running

Build the React UI once (and again after frontend changes), then start the server:

```bash
npm --prefix frontend run build
fastapi dev main.py
```

- Web UI: http://127.0.0.1:8000/ (the built React app)
- Legacy single-file UI: http://127.0.0.1:8000/classic
- Interactive API docs: http://127.0.0.1:8000/docs

For frontend work with hot reload, run the Vite dev server alongside the API instead of rebuilding:

```bash
npm --prefix frontend run dev     # http://localhost:5173 — calls the API on :8000
```

Run the test suite:

```bash
python -m pytest -q
```

## Deploying

The whole site is one FastAPI process serving both the API and the web UI:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Keep it to a **single instance/worker** — game state lives in an in-memory dict, so separate processes would each hold their own separate set of games.

`render.yaml` is a ready-made [Render](https://render.com) blueprint: in the Render dashboard choose **New → Blueprint**, point it at this repo, and it deploys the free-tier service — the build step installs the Python deps, then runs `npm ci` + `npm run build` in `frontend/` so FastAPI can serve the built app (games are lost on restart/redeploy; the free tier also sleeps after idle periods).

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

Bots advance automatically server-side: every call runs the bots until the next decision the human must make, then returns the state paused there. The response includes the current `phase` (what input is expected), an `events` list describing what just happened, and a per-hand `log` of human-readable lines (public ones plus your own private ones, e.g. your secret shuffle choice).

## Project layout

| Path | Responsibility |
|---|---|
| `main.py` | FastAPI app — endpoints, request models, per-game locks, serves the built UI |
| `frontend/` | React web UI (Vite) — built to `frontend/dist`, served at `/` |
| `index.html` | Legacy single-file vanilla-JS UI, served at `/classic` |
| `game/engine.py` | Pure state-machine engine — the source of truth for game logic |
| `game/card.py` | `Card`, `Suit`, `Deck` |
| `game/hand_evaluator.py` | `HandEvaluator.best_hand()` — scores the best 5 of N cards |
| `game/cheat_system.py` | Cheat-hand constants and shuffle-timing distributions |
| `game/roles.py` | Role definitions and descriptions |
| `play.py` | Terminal launcher for the legacy CLI game |
| `tests/` | pytest suite (191 tests) |

The engine is a pure state machine: no I/O and no classes, with all game state held in one JSON-serialisable dict that is returned verbatim as the API response. See [CLAUDE.md](CLAUDE.md) for the full architecture notes.

## Status

Work in progress. The FastAPI engine and web UI are the active implementation; the older standard-library CLI modules (`game/texas_holdem.py`, `game/player.py`) are legacy, kept playable in a terminal via `python play.py`.
