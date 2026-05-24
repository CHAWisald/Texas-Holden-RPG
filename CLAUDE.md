# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running

```bash
python main.py
```

No external dependencies — standard library only. No build step, test suite, or package manager config.

## Architecture

The game is a CLI Texas Hold'em implementation with a social deduction "cheat detection" mechanic layered on top of standard poker.

**Data flow per hand:**

1. `main.py` builds a `HumanPlayer` + up to 5 `BotPlayer` instances and hands them to `TexasHoldem`.
2. `TexasHoldem.play_hand()` orchestrates the full hand lifecycle: shuffle phase → accusation phase → deal → pre-flop → flop → turn → river → showdown.
3. Before cards are dealt, `CheatSystem` runs a three-phase mini-game:
   - **Shuffle phase** — the dealer secretly calls `player.decide_to_cheat()`. If cheating, a time is drawn from `CHEAT_RANGE` (15–20 s); otherwise from `HONEST_RANGE` (12.5–17.5 s). The ranges overlap deliberately to create uncertainty.
   - **Accusation phase** — every other player sees the displayed shuffle time and may call the prosecutor (costs `2 × big_blind`). Only the first accuser proceeds.
   - **Resolution** — if accused and guilty, the dealer pays a penalty and the hand is re-dealt fairly; if falsely accused, the accuser pays the dealer.
4. If uncaught cheating occurred, `CheatSystem.deal_cheat_hand()` surgically removes the chosen two cards from the deck before normal dealing resumes.

**Module responsibilities:**

| File | Responsibility |
|---|---|
| `game/card.py` | `Card` (rank 2–14, `Suit` enum), `Deck` (shuffle + deal) |
| `game/hand_evaluator.py` | `HandEvaluator.best_hand()` — scores any 5-of-N card subset via `combinations`; returns `(score_tuple, hand_name)` |
| `game/player.py` | `Player` base → `HumanPlayer` (stdin with timeout), `BotPlayer` (aggression-weighted heuristic using hand strength) |
| `game/cheat_system.py` | `CheatSystem` (the three phases above) + `timed_input()` (cross-platform stdin with timeout) |
| `game/texas_holdem.py` | `TexasHoldem` — game loop, betting rounds (`deque`-based re-queuing on raises), showdown, split-pot logic |

**Bot logic:** `BotPlayer._hand_strength()` maps `HandEvaluator` output to a 0–1 float; pre-flop it uses a rank/suit heuristic. Raise/call/fold thresholds are offset by the bot's `aggression` parameter (0.3–0.8 across the five named bots).

**`timed_input()`** uses `select.select` on POSIX for non-blocking stdin; falls back to plain `input()` on Windows/non-TTY (tests).

## Key design decisions

- Ace rank is stored as 14; `HandEvaluator._check_straight` handles the ace-low wheel (A-2-3-4-5) by remapping to `[5,4,3,2,1]`.
- `street_bet` on each player tracks chips committed this street only; it is reset by `_reset_street()` between streets (not between raises).
- Dealer rotation uses an index into the alive-players list, recalculated each hand so eliminated players are skipped.
