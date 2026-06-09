"""
game/engine.py — Pure state-machine engine for Texas Hold'em.

No print(), no input(), no blocking I/O in this file.
All game state is a JSON-serialisable dict.
Random is used for shuffle, bot decisions, and role effects.
"""

import random
from itertools import combinations
from typing import Optional

from .card import Card, Deck, Suit
from .hand_evaluator import HandEvaluator
from .cheat_system import (
    CHEAT_HANDS, CHEAT_HAND_OPTIONS,
    HONEST_RANGE, HONEST_ALPHA, HONEST_BETA, SHUFFLE_STD,
)


# ── Phases ─────────────────────────────────────────────────────────────────────

PHASE_WAITING    = "WAITING"
PHASE_SHUFFLE    = "SHUFFLE_PHASE"      # human dealer must call /shuffle
PHASE_ACCUSATION = "ACCUSATION_PHASE"   # a human non-dealer must call /accuse
PHASE_PREFLOP    = "PREFLOP_BETTING"
PHASE_FLOP       = "FLOP_BETTING"
PHASE_TURN       = "TURN_BETTING"
PHASE_RIVER      = "RIVER_BETTING"
PHASE_HAND_OVER  = "HAND_OVER"          # hand resolved; call /start-hand for next
PHASE_GAME_OVER  = "GAME_OVER"

BETTING_PHASES = {PHASE_PREFLOP, PHASE_FLOP, PHASE_TURN, PHASE_RIVER}


# ── Card / deck helpers ────────────────────────────────────────────────────────

def _c2d(card: Card) -> dict:
    return {"rank": card.rank, "suit": card.suit.value}


def _d2c(d: dict) -> Card:
    return Card(d["rank"], Suit(d["suit"]))


def _fresh_deck() -> list:
    return [_c2d(c) for c in Deck().cards]


def _deal_n(state: dict, n: int) -> list:
    cards = state["deck"][:n]
    state["deck"] = state["deck"][n:]
    return cards


def _remove_from_deck(state: dict, cards: list):
    for c in cards:
        try:
            state["deck"].remove(c)
        except ValueError:
            pass


# ── Event log ──────────────────────────────────────────────────────────────────

def _emit(state: dict, event_type: str, **data):
    state.setdefault("events", []).append({"type": event_type, **data})


# ── Player helpers ─────────────────────────────────────────────────────────────

def _new_player(pid: str, name: str, is_human: bool,
                chips: int = 1000, aggression: float = 0.5,
                role: Optional[str] = None) -> dict:
    return {
        "id": pid,
        "name": name,
        "chips": chips,
        "hole_cards": [],
        "street_bet": 0,
        "folded": False,
        "all_in": False,
        "is_human": is_human,
        "aggression": aggression,
        "role": role,
        # Cursed state
        "is_devil": False,
        "devil_debt": 0,
        "devil_hands": 0,
        "has_cursed": False,
        "curse_hands_left": 0,
        # Gunner state
        "bullets_used": 0,
        "died_by_revolver": False,
        "gun_bullet_chamber": random.randint(0, 5),
        "gun_current_chamber": 0,
    }


def _get_player(state: dict, pid: str) -> Optional[dict]:
    for p in state["players"]:
        if p["id"] == pid:
            return p
    return None


def _active(state: dict) -> list:
    """Players who can start a new hand (chips > 0)."""
    return [p for p in state["players"] if p["chips"] > 0]


def _still_in(state: dict) -> list:
    """Players not yet folded in the current hand."""
    return [p for p in state["players"] if not p["folded"]]


# ── Betting helpers ────────────────────────────────────────────────────────────

def _place_bet(state: dict, p: dict, amount: int) -> int:
    amount = min(amount, p["chips"])
    p["chips"]     -= amount
    p["street_bet"] += amount
    state["pot"]    += amount
    if p["chips"] == 0:
        p["all_in"] = True
    return amount


def _reset_street(state: dict):
    for p in state["players"]:
        p["street_bet"] = 0


def _fold_dead_players(state: dict):
    """Fold anyone shot dead (chips=0, not all-in) mid-hand."""
    for p in state["players"]:
        if p["chips"] == 0 and not p["folded"] and not p["all_in"]:
            p["folded"] = True
            _emit(state, "dead_fold", player_id=p["id"])


# ── Bot decision helpers ───────────────────────────────────────────────────────

def _bot_preflop_strength(p: dict) -> float:
    if len(p["hole_cards"]) < 2:
        return 0.3
    r1 = p["hole_cards"][0]["rank"]
    r2 = p["hole_cards"][1]["rank"]
    s1 = p["hole_cards"][0]["suit"]
    s2 = p["hole_cards"][1]["suit"]
    high, low = max(r1, r2), min(r1, r2)
    suited = (s1 == s2)
    if r1 == r2:
        return 0.50 + (r1 - 2) / 12.0 * 0.45
    base = (high - 2) / 12.0 * 0.55 + (low - 2) / 12.0 * 0.25
    gap = high - low
    if suited:   base += 0.05
    if gap == 1: base += 0.04
    elif gap == 2: base += 0.02
    return min(0.72, base)


def _bot_hand_strength(p: dict, community_cards: list) -> float:
    hole  = [_d2c(c) for c in p["hole_cards"]]
    board = [_d2c(c) for c in community_cards]
    all_cards = hole + board

    if not board:
        return _bot_preflop_strength(p)
    if len(all_cards) < 5:
        return (_bot_preflop_strength(p) + 0.3) / 2.0

    result = HandEvaluator.best_hand(all_cards)
    if result is None:
        return 0.1

    score, hand_name = result
    base = {
        'High Card': 0.10, 'One Pair': 0.25, 'Two Pair': 0.45,
        'Three of a Kind': 0.60, 'Straight': 0.70, 'Flush': 0.75,
        'Full House': 0.85, 'Four of a Kind': 0.95,
        'Straight Flush': 0.98, 'Royal Flush': 1.00,
    }[hand_name]
    kicker_bonus = (score[1][0] / 14.0) * 0.04 if score[1] else 0.0
    return min(1.0, base + kicker_bonus)


def _bot_action(state: dict, p: dict) -> tuple:
    current_bet = state["current_bet"]
    to_call     = current_bet - p["street_bet"]
    min_raise   = state["min_raise"]
    pot         = state["pot"]
    strength    = _bot_hand_strength(p, state["community_cards"])
    agg         = p.get("aggression", 0.5)

    pot_odds     = to_call / (pot + to_call) if to_call > 0 and pot > 0 else 0.0
    raise_thresh = 0.65 - agg * 0.15
    call_thresh  = 0.35 - agg * 0.10

    if strength >= raise_thresh and p["chips"] > to_call + min_raise:
        raise_size = max(min_raise, int(pot * 0.6 * strength))
        raise_size = min(raise_size, p["chips"] - to_call)
        if raise_size >= min_raise:
            return ("raise", raise_size)

    if strength >= call_thresh or (to_call > 0 and strength > pot_odds * 1.2):
        if to_call == 0:
            return ("check", 0)
        if to_call >= p["chips"]:
            return ("all-in", p["chips"]) if strength >= 0.35 else ("fold", 0)
        return ("call", to_call)

    if to_call == 0:
        return ("check", 0)
    return ("fold", 0)


def _bot_decide_cheat(p: dict) -> tuple:
    agg = p.get("aggression", 0.5)
    if random.random() < agg * 0.25:
        n = len(CHEAT_HAND_OPTIONS)
        weights = [n - i for i in range(n)] if agg >= 0.6 else [i + 1 for i in range(n)]
        chosen = random.choices(CHEAT_HAND_OPTIONS, weights=weights, k=1)[0]
        return True, chosen
    return False, None


def _bot_decide_accuse(p: dict, elapsed: float, big_blind: int) -> bool:
    if p["chips"] < 2 * big_blind:
        return False
    if   elapsed > 19.5: prob = 0.92
    elif elapsed > 18.0: prob = 0.80
    elif elapsed > 17.0: prob = 0.40
    elif elapsed > 16.0: prob = 0.18
    elif elapsed > 15.0: prob = 0.07
    else:                prob = 0.02
    return random.random() < prob


def _generate_elapsed(cheated: bool, chosen_hand: Optional[str]) -> float:
    if cheated and chosen_hand:
        h = CHEAT_HANDS[chosen_hand]
        return max(h.lo, min(h.hi, random.gauss(h.mean, SHUFFLE_STD)))
    lo, hi = HONEST_RANGE
    return lo + random.betavariate(HONEST_ALPHA, HONEST_BETA) * (hi - lo)


# ── Cheat-hand dealing ─────────────────────────────────────────────────────────

_PAIR_RANK     = {'AA': 14, 'KK': 13, 'QQ': 12, 'JJ': 11, 'TT': 10, '99': 9, '88': 8}
_SUITED_RANKS  = {'AKs': (14, 13), 'AQs': (14, 12), 'KQs': (13, 12)}
_OFFSUIT_RANKS = {'AKo': (14, 13), 'AQo': (14, 12)}


def _select_cheat_cards(hand_name: str, deck: list) -> list:
    if hand_name in _PAIR_RANK:
        rank = _PAIR_RANK[hand_name]
        return [c for c in deck if c["rank"] == rank][:2]

    if hand_name in _SUITED_RANKS:
        r1, r2 = _SUITED_RANKS[hand_name]
        for suit_val in [s.value for s in Suit]:
            a = next((c for c in deck if c["rank"] == r1 and c["suit"] == suit_val), None)
            b = next((c for c in deck if c["rank"] == r2 and c["suit"] == suit_val), None)
            if a and b:
                return [a, b]
        r1, r2 = _SUITED_RANKS[hand_name]  # fall through to offsuit
    elif hand_name in _OFFSUIT_RANKS:
        r1, r2 = _OFFSUIT_RANKS[hand_name]
    else:
        return []

    c1    = next((c for c in deck if c["rank"] == r1), None)
    c2_os = [c for c in deck if c["rank"] == r2 and (not c1 or c["suit"] != c1["suit"])]
    c2    = c2_os[0] if c2_os else next((c for c in deck if c["rank"] == r2), None)
    return [c1, c2] if c1 and c2 else []


def _deal_cheat_hand(state: dict, hand_name: str) -> list:
    cards = _select_cheat_cards(hand_name, state["deck"])
    _remove_from_deck(state, cards)
    return cards


# ── Role effect helpers ────────────────────────────────────────────────────────

def _lucky_deal(state: dict, p: dict) -> list:
    """Deal 3 cards, auto-keep the 2 with the highest combined rank."""
    cards = _deal_n(state, 3)
    best_pair = max(combinations(range(3), 2),
                    key=lambda pair: cards[pair[0]]["rank"] + cards[pair[1]]["rank"])
    kept      = [cards[i] for i in best_pair]
    discarded = [cards[i] for i in range(3) if i not in best_pair]
    state["deck"].extend(discarded)
    return kept


def _draw_junk_from_deck(deck: list, avoid_rank: int) -> Optional[dict]:
    candidates = [c for c in deck if c["rank"] != avoid_rank and c["rank"] <= 7]
    if not candidates:
        candidates = [c for c in deck if c["rank"] != avoid_rank]
    return random.choice(candidates) if candidates else None


def _apply_devil_hand(state: dict, p: dict):
    """70% chance devil tampers with the in-devil-state player's hole cards."""
    if random.random() > 0.70:
        return
    hole = p["hole_cards"]
    if len(hole) < 2:
        return

    if random.random() < 0.50:
        # Downgrade: break pair or replace high card with junk
        if hole[0]["rank"] == hole[1]["rank"]:
            junk = _draw_junk_from_deck(state["deck"], avoid_rank=hole[0]["rank"])
            idx  = 0
        else:
            idx  = 0 if hole[0]["rank"] > hole[1]["rank"] else 1
            junk = _draw_junk_from_deck(state["deck"], avoid_rank=hole[idx]["rank"])
        if junk:
            old = hole[idx]
            hole[idx] = junk
            _remove_from_deck(state, [junk])
            state["deck"].append(old)
            _emit(state, "devil_tamper", player_id=p["id"], subtype="downgrade")
    else:
        # Swap one random card
        idx  = random.randint(0, len(hole) - 1)
        junk = _draw_junk_from_deck(state["deck"], avoid_rank=hole[idx]["rank"])
        if junk:
            old = hole[idx]
            hole[idx] = junk
            _remove_from_deck(state, [junk])
            state["deck"].append(old)
            _emit(state, "devil_tamper", player_id=p["id"], subtype="swap")


def _apply_victim_curse(state: dict, p: dict):
    """Same tampering logic applied to a cursed victim each hand."""
    if random.random() > 0.70:
        return
    hole = p["hole_cards"]
    if len(hole) < 2:
        return

    if random.random() < 0.50:
        idx  = 0 if hole[0]["rank"] > hole[1]["rank"] else 1
        junk = _draw_junk_from_deck(state["deck"], avoid_rank=hole[idx]["rank"])
        if junk:
            old = hole[idx]
            hole[idx] = junk
            _remove_from_deck(state, [junk])
            state["deck"].append(old)
            _emit(state, "curse_tamper", player_id=p["id"], subtype="downgrade")
    else:
        idx  = random.randint(0, len(hole) - 1)
        junk = _draw_junk_from_deck(state["deck"], avoid_rank=hole[idx]["rank"])
        if junk:
            old = hole[idx]
            hole[idx] = junk
            _remove_from_deck(state, [junk])
            state["deck"].append(old)
            _emit(state, "curse_tamper", player_id=p["id"], subtype="swap")


def _fire_revolver(p: dict) -> bool:
    fired = (p["gun_current_chamber"] == p["gun_bullet_chamber"])
    p["gun_current_chamber"] = (p["gun_current_chamber"] + 1) % 6
    return fired


def _reload_revolver(p: dict):
    p["gun_bullet_chamber"]  = random.randint(0, 5)
    p["gun_current_chamber"] = 0


def _lucky_immune(p: dict) -> bool:
    return p.get("role") == "LUCKY" and random.random() < 0.30


def _tick_devil_debts(state: dict):
    for p in state["players"]:
        if not p.get("is_devil") or p.get("devil_debt", 0) <= 0:
            continue
        p["devil_hands"] -= 1
        if p["devil_hands"] <= 0:
            if p["chips"] >= p["devil_debt"]:
                p["chips"]     -= p["devil_debt"]
                p["is_devil"]   = False
                p["devil_debt"] = 0
                _emit(state, "devil_debt_repaid", player_id=p["id"])
            else:
                p["chips"]     = 0
                p["is_devil"]  = False
                p["devil_debt"] = 0
                _emit(state, "devil_debt_eliminated", player_id=p["id"])


def _handle_bust(state: dict, p: dict) -> bool:
    """Auto-process a bust. Returns True if player is revived."""
    role = p.get("role")
    bb   = state["big_blind"]

    if role == "CURSED" and not p.get("is_devil"):
        loan   = bb * 20
        debt   = bb * 25
        period = random.randint(5, 8)
        p["chips"]       = loan
        p["is_devil"]    = True
        p["devil_debt"]  = debt
        p["devil_hands"] = period
        _emit(state, "devil_deal", player_id=p["id"],
              loan=loan, debt=debt, hands=period)
        return True

    if role == "GUNNER" and not p.get("died_by_revolver"):
        p["bullets_used"] += 1
        if _fire_revolver(p):
            p["died_by_revolver"] = True
            _emit(state, "revolver_bang", player_id=p["id"])
            return False
        chips_gained = bb * 20
        p["chips"] += chips_gained
        _emit(state, "revolver_click", player_id=p["id"],
              chips_gained=chips_gained)
        return True

    return False


# ── Ability actions ────────────────────────────────────────────────────────────

def _do_shoot(state: dict, shooter: dict, target_id: Optional[str]):
    bb           = state["big_blind"]
    bullets_used = shooter.get("bullets_used", 0)
    cost         = bb * 10 * (2 ** bullets_used)

    if shooter["chips"] < cost:
        _emit(state, "ability_failed", player_id=shooter["id"],
              reason="insufficient_chips", cost_needed=cost)
        return

    shooter["chips"]       -= cost
    shooter["bullets_used"] = bullets_used + 1

    if target_id is None:
        # Self-shoot
        if _fire_revolver(shooter):
            shooter["died_by_revolver"] = True
            shooter["chips"] = 0
            _emit(state, "revolver_bang", player_id=shooter["id"])
        else:
            _emit(state, "revolver_click", player_id=shooter["id"])
        return

    target = _get_player(state, target_id)
    if target is None or target["chips"] <= 0:
        return

    if _lucky_immune(target):
        _emit(state, "lucky_immune", target_id=target_id, effect="shot")
        return

    if _fire_revolver(shooter):
        target["chips"] = 0
        _reload_revolver(shooter)
        _emit(state, "shot_hit", shooter_id=shooter["id"],
              target_id=target_id, cost=cost)
    else:
        _emit(state, "shot_miss", shooter_id=shooter["id"],
              target_id=target_id, cost=cost)


def _do_curse(state: dict, cursed_player: dict, target_id: Optional[str]):
    if cursed_player.get("has_cursed"):
        _emit(state, "ability_failed", player_id=cursed_player["id"],
              reason="already_used")
        return

    cursed_player["has_cursed"] = True

    if target_id is None:
        others = [p for p in state["players"]
                  if p["id"] != cursed_player["id"] and p["chips"] > 0]
        if not others:
            return
        target = max(others, key=lambda p: p["chips"])
    else:
        target = _get_player(state, target_id)
        if target is None:
            return

    if _lucky_immune(target):
        _emit(state, "lucky_immune", target_id=target["id"], effect="curse")
        return

    duration = random.randint(3, 5)
    target["curse_hands_left"] = duration
    _emit(state, "cursed", by=cursed_player["id"],
          target_id=target["id"], hands=duration)


def _maybe_bluff_reward(state: dict, winner: dict):
    """Forgive 5BB debt when Cursed-devil wins uncontested with a weak hand."""
    if not winner.get("is_devil") or winner.get("devil_debt", 0) <= 0:
        return
    board = [_d2c(c) for c in state["community_cards"]]
    hole  = [_d2c(c) for c in winner["hole_cards"]]
    if len(hole + board) < 5:
        return
    result = HandEvaluator.best_hand(hole + board)
    if result and result[1] in ("High Card", "One Pair"):
        forgive = 5 * state["big_blind"]
        winner["devil_debt"] = max(0, winner["devil_debt"] - forgive)
        if winner["devil_debt"] == 0:
            winner["is_devil"] = False
        _emit(state, "bluff_reward", player_id=winner["id"], forgiven=forgive,
              remaining_debt=winner["devil_debt"])


# ── Action logic ───────────────────────────────────────────────────────────────

def _do_action(state: dict, p: dict, action: str, amount: int):
    current_bet = state["current_bet"]
    to_call     = current_bet - p["street_bet"]
    min_raise   = state["min_raise"]

    if action == "fold":
        p["folded"] = True
        _emit(state, "fold", player_id=p["id"])

    elif action == "check":
        if to_call > 0:
            raise ValueError(
                f"Cannot check — {p['name']} must call {to_call} chips, raise, or fold"
            )
        _emit(state, "check", player_id=p["id"])

    elif action == "call":
        actual = _place_bet(state, p, to_call)
        _emit(state, "call", player_id=p["id"], amount=actual, pot=state["pot"])

    elif action == "raise":
        # Enforce minimum raise of 1BB; clip up if player has enough chips
        if amount < state["big_blind"] and to_call + state["big_blind"] <= p["chips"]:
            amount = state["big_blind"]
        actual  = _place_bet(state, p, to_call + amount)
        new_bet = p["street_bet"]
        if new_bet > current_bet:
            state["min_raise"]   = state["big_blind"]   # always 1BB
            state["current_bet"] = new_bet
            # Re-queue everyone else in original street order
            state["to_act"] = [
                pid for pid in state["street_player_order"]
                if pid != p["id"]
                and not _get_player(state, pid)["folded"]
                and not _get_player(state, pid)["all_in"]
            ]
            _emit(state, "raise", player_id=p["id"],
                  amount=new_bet, pot=state["pot"])
        else:
            _emit(state, "all_in", player_id=p["id"],
                  amount=actual, pot=state["pot"])

    elif action == "all-in":
        actual  = _place_bet(state, p, p["chips"])
        new_bet = p["street_bet"]
        if new_bet > current_bet:
            state["current_bet"] = new_bet
            state["min_raise"]   = state["big_blind"]   # always 1BB
            state["to_act"] = [
                pid for pid in state["street_player_order"]
                if pid != p["id"]
                and not _get_player(state, pid)["folded"]
                and not _get_player(state, pid)["all_in"]
            ]
        _emit(state, "all_in", player_id=p["id"],
              amount=new_bet, pot=state["pot"])

    else:
        raise ValueError(f"Unknown action: {action!r}")


# ── Internal phase transitions ─────────────────────────────────────────────────

def _after_shuffle_decision(state: dict, dealer: dict, cheated: bool,
                             chosen_hand: Optional[str], utg_pos: int) -> dict:
    elapsed             = _generate_elapsed(cheated, chosen_hand)
    state["cheated"]    = cheated
    state["chosen_hand"] = chosen_hand
    state["cheat_elapsed"] = elapsed
    state["_utg_pos"]   = utg_pos

    _emit(state, "shuffle_done", dealer_id=dealer["id"],
          elapsed=round(elapsed, 2), cheated=cheated, chosen_hand=chosen_hand)

    cost   = 2 * state["big_blind"]
    active = [_get_player(state, pid) for pid in state["hand_active_ids"]]
    state["accusation_order"] = [
        p["id"] for p in active
        if p["id"] != dealer["id"]
        and not p["folded"]
        and p["chips"] >= cost
    ]
    return _advance_accusation(state)


def _advance_accusation(state: dict) -> dict:
    """Process bot accusers; pause at first human accuser in line."""
    elapsed   = state["cheat_elapsed"]
    big_blind = state["big_blind"]
    cost      = 2 * big_blind

    while state["accusation_order"]:
        pid = state["accusation_order"][0]
        p   = _get_player(state, pid)

        if p["is_human"]:
            state["phase"] = PHASE_ACCUSATION
            _emit(state, "accusation_prompt", player_id=pid,
                  elapsed=round(elapsed, 2), cost=cost)
            return state

        state["accusation_order"].pop(0)
        if _bot_decide_accuse(p, elapsed, big_blind) and p["chips"] >= cost:
            p["chips"]      -= cost
            state["accusers"] = [pid]
            _emit(state, "bot_accused", accuser_id=pid, cost=cost)
            return _resolve_and_deal(state)

        _emit(state, "passed_accusation", player_id=pid)

    state["accusers"] = state.get("accusers") or []
    return _resolve_and_deal(state)


def _resolve_and_deal(state: dict) -> dict:
    """Resolve accusation, deal cards, apply role effects, start preflop."""
    active   = [_get_player(state, pid) for pid in state["hand_active_ids"]]
    dealer   = active[state["dealer_pos"]]
    accusers = state["accusers"]
    cheated  = state["cheated"]

    caught = False
    if accusers:
        accuser = _get_player(state, accusers[0])
        cost    = 2 * state["big_blind"]
        # Lucky dealer escape (30%)
        if dealer.get("role") == "LUCKY" and random.random() < 0.30:
            accuser["chips"] += cost
            _emit(state, "lucky_escape", dealer_id=dealer["id"])
        elif cheated:
            penalty        = min(cost, dealer["chips"])
            dealer["chips"] -= penalty
            accuser["chips"] += cost + penalty
            caught = True
            _emit(state, "caught_cheating", dealer_id=dealer["id"],
                  accuser_id=accuser["id"], penalty=penalty)
        else:
            dealer["chips"] += cost
            _emit(state, "false_accusation", dealer_id=dealer["id"],
                  accuser_id=accuser["id"])

    if caught:
        state["deck"] = _fresh_deck()
        for p in active:
            p["hole_cards"] = _deal_n(state, 2)
    else:
        for p in active:
            if cheated and p["id"] == dealer["id"]:
                p["hole_cards"] = _deal_cheat_hand(state, state["chosen_hand"])
            elif p.get("role") == "LUCKY":
                p["hole_cards"] = _lucky_deal(state, p)
            else:
                p["hole_cards"] = _deal_n(state, 2)

    for p in active:
        if p.get("is_devil"):
            _apply_devil_hand(state, p)
        if p.get("curse_hands_left", 0) > 0:
            _apply_victim_curse(state, p)
            p["curse_hands_left"] -= 1

    _emit(state, "dealt")

    utg_pos  = state["_utg_pos"]
    n        = len(active)
    preflop  = [active[(utg_pos + i) % n]["id"] for i in range(n)]

    state["current_bet"]          = state["big_blind"]
    state["min_raise"]            = state["big_blind"]
    state["phase"]                = PHASE_PREFLOP
    state["street_player_order"]  = preflop
    state["to_act"]               = [
        pid for pid in preflop
        if not _get_player(state, pid)["folded"]
        and not _get_player(state, pid)["all_in"]
    ]

    _emit(state, "preflop_start", current_bet=state["current_bet"])
    return _advance_betting(state)


def _advance_betting(state: dict) -> dict:
    """Process bot turns until a human must act or the round ends."""
    while state["to_act"]:
        if len(_still_in(state)) <= 1:
            break

        pid = state["to_act"][0]
        p   = _get_player(state, pid)

        if p["folded"] or p["all_in"]:
            state["to_act"].pop(0)
            continue

        if p["is_human"]:
            return state   # pause for human input

        state["to_act"].pop(0)

        # Bot role ability (5% chance)
        if p.get("role") == "GUNNER" and random.random() < 0.05:
            targets = [q for q in state["players"]
                       if q["id"] != p["id"] and q["chips"] > 0]
            if targets:
                _do_shoot(state, p, random.choice(targets)["id"])
                _fold_dead_players(state)
        elif p.get("role") == "CURSED" and not p.get("has_cursed") and random.random() < 0.05:
            targets = [q for q in state["players"]
                       if q["id"] != p["id"] and q["chips"] > 0]
            if targets:
                _do_curse(state, p, random.choice(targets)["id"])

        if p["folded"] or p["all_in"] or p["chips"] == 0:
            if p["chips"] == 0:
                p["folded"] = True
            continue

        if len(_still_in(state)) <= 1:
            break

        action, amount = _bot_action(state, p)
        _do_action(state, p, action, amount)
        _fold_dead_players(state)

    return _end_street(state)


def _end_street(state: dict) -> dict:
    remaining = _still_in(state)

    if len(remaining) <= 1:
        return _end_hand(state)

    phase = state["phase"]

    if phase == PHASE_PREFLOP:
        _reset_street(state)
        state["community_cards"] += _deal_n(state, 3)
        _emit(state, "flop", community_cards=state["community_cards"])
        return _start_postflop(state, PHASE_FLOP)

    if phase == PHASE_FLOP:
        _reset_street(state)
        state["community_cards"] += _deal_n(state, 1)
        _emit(state, "turn", community_cards=state["community_cards"])
        return _start_postflop(state, PHASE_TURN)

    if phase == PHASE_TURN:
        _reset_street(state)
        state["community_cards"] += _deal_n(state, 1)
        _emit(state, "river", community_cards=state["community_cards"])
        return _start_postflop(state, PHASE_RIVER)

    if phase == PHASE_RIVER:
        return _end_hand(state)

    return state


def _start_postflop(state: dict, phase: str) -> dict:
    active     = [_get_player(state, pid) for pid in state["hand_active_ids"]]
    dealer_pos = state["dealer_pos"]
    n          = len(active)

    order = [
        active[(dealer_pos + i) % n]["id"]
        for i in range(1, n + 1)
        if not active[(dealer_pos + i) % n]["folded"]
        and not active[(dealer_pos + i) % n]["all_in"]
    ]

    state["phase"]               = phase
    state["current_bet"]         = 0
    state["min_raise"]           = state["big_blind"]
    state["street_player_order"] = order
    state["to_act"]              = list(order)

    _emit(state, "street_start", phase=phase,
          community_cards=state["community_cards"])

    if not order:
        return _end_street(state)   # all remaining are all-in

    return _advance_betting(state)


def _end_hand(state: dict) -> dict:
    remaining = _still_in(state)

    if len(remaining) == 1:
        w = remaining[0]
        w["chips"] += state["pot"]
        state["hand_result"] = {"type": "fold_win",
                                 "winner_ids": [w["id"]], "pot": state["pot"]}
        _emit(state, "hand_over", type="fold_win",
              winner_ids=[w["id"]], pot=state["pot"])
        _maybe_bluff_reward(state, w)
    else:
        _showdown(state)

    # Handle newly busted players
    for p in state["players"]:
        if p["chips"] == 0:
            _handle_bust(state, p)

    # Advance dealer
    active = _active(state)
    if active:
        state["dealer_idx"] = (state["dealer_idx"] + 1) % len(active)

    # Devil debt countdown
    _tick_devil_debts(state)

    active = _active(state)
    state["phase"] = PHASE_GAME_OVER if len(active) < 2 else PHASE_HAND_OVER
    return state


def _showdown(state: dict) -> dict:
    remaining = _still_in(state)
    board     = [_d2c(c) for c in state["community_cards"]]

    results = []
    for p in remaining:
        hole = [_d2c(c) for c in p["hole_cards"]]
        score, hand_name = HandEvaluator.best_hand(hole + board)
        results.append((score, p, hand_name))

    best   = max(r[0] for r in results)
    winners = [(p, hn) for score, p, hn in results if score == best]

    share     = state["pot"] // len(winners)
    remainder = state["pot"] %  len(winners)
    for w, _ in winners:
        w["chips"] += share
    winners[0][0]["chips"] += remainder

    winner_ids = [w["id"] for w, _ in winners]
    all_hands  = {p["id"]: hn for _, p, hn in results}

    state["hand_result"] = {
        "type":       "showdown",
        "winner_ids": winner_ids,
        "pot":        state["pot"],
        "all_hands":  all_hands,
    }
    _emit(state, "showdown", winner_ids=winner_ids,
          pot=state["pot"], all_hands=all_hands)
    return state


# ── Public API ─────────────────────────────────────────────────────────────────

def create_game(players_config: list,
                small_blind: int = 10,
                big_blind:   int = 20) -> dict:
    """
    Build initial game state from a list of player configs.

    Each config dict requires: id (str), name (str), is_human (bool).
    Optional: chips (int, default 1000), aggression (float, default 0.5),
              role (str|None — "CURSED", "GUNNER", "LUCKY").
    """
    players = [
        _new_player(
            pid=c["id"], name=c["name"], is_human=c["is_human"],
            chips=c.get("chips", 1000),
            aggression=c.get("aggression", 0.5),
            role=c.get("role"),
        )
        for c in players_config
    ]
    return {
        "phase":        PHASE_WAITING,
        "players":      players,
        "community_cards": [],
        "deck":         [],
        "pot":          0,
        "dealer_idx":   0,
        "small_blind":  small_blind,
        "big_blind":    big_blind,
        "hand_num":     0,
        # Betting
        "current_bet":  0,
        "min_raise":    big_blind,
        "to_act":       [],
        "street_player_order": [],
        # Hand-scoped (set each hand)
        "hand_active_ids": [],
        "dealer_pos":   0,
        "_utg_pos":     0,
        # Cheat phase
        "cheat_elapsed": None,
        "cheated":       False,
        "chosen_hand":   None,
        "accusation_order": [],
        "accusers":      [],
        # Result
        "hand_result":   None,
        "events":        [],
    }


def start_hand(state: dict) -> dict:
    """
    Set up a new hand and advance to the first human decision point.
    Valid in WAITING or HAND_OVER phases.
    Returns state in SHUFFLE_PHASE, ACCUSATION_PHASE, a BETTING phase,
    HAND_OVER (if hand resolved immediately), or GAME_OVER.
    """
    if state["phase"] not in (PHASE_WAITING, PHASE_HAND_OVER):
        raise ValueError(f"Cannot start hand in phase {state['phase']!r}")

    state["events"] = []

    active = _active(state)
    if len(active) < 2:
        state["phase"] = PHASE_GAME_OVER
        winner = active[0] if active else None
        _emit(state, "game_over",
              winner_id=winner["id"] if winner else None,
              winner_chips=winner["chips"] if winner else 0)
        return state

    state["hand_num"]        += 1
    state["pot"]              = 0
    state["community_cards"]  = []
    state["cheated"]          = False
    state["chosen_hand"]      = None
    state["cheat_elapsed"]    = None
    state["accusation_order"] = []
    state["accusers"]         = []
    state["hand_result"]      = None
    state["current_bet"]      = 0
    state["min_raise"]        = state["big_blind"]
    state["to_act"]           = []
    state["street_player_order"] = []

    for p in active:
        p["hole_cards"]  = []
        p["street_bet"]  = 0
        p["folded"]      = False
        p["all_in"]      = False

    n          = len(active)
    dealer_pos = state["dealer_idx"] % n

    if n == 2:
        sb_pos  = dealer_pos
        bb_pos  = (dealer_pos + 1) % n
        utg_pos = dealer_pos
    else:
        sb_pos  = (dealer_pos + 1) % n
        bb_pos  = (dealer_pos + 2) % n
        utg_pos = (dealer_pos + 3) % n

    dealer    = active[dealer_pos]
    sb_player = active[sb_pos]
    bb_player = active[bb_pos]

    state["hand_active_ids"] = [p["id"] for p in active]
    state["dealer_pos"]      = dealer_pos

    _place_bet(state, sb_player, state["small_blind"])
    _place_bet(state, bb_player, state["big_blind"])

    _emit(state, "hand_start",
          hand_num=state["hand_num"],
          dealer_id=dealer["id"],
          sb_id=sb_player["id"], sb_bet=state["small_blind"],
          bb_id=bb_player["id"], bb_bet=state["big_blind"],
          pot=state["pot"])

    state["deck"] = _fresh_deck()

    if dealer["is_human"]:
        state["phase"] = PHASE_SHUFFLE
        _emit(state, "shuffle_phase",
              dealer_id=dealer["id"],
              cheat_hand_options=list(CHEAT_HAND_OPTIONS),
              cheat_hand_info={k: {"label": v.label, "lo": v.lo, "hi": v.hi}
                               for k, v in CHEAT_HANDS.items()})
        return state

    cheated, chosen_hand = _bot_decide_cheat(dealer)
    return _after_shuffle_decision(state, dealer, cheated, chosen_hand, utg_pos)


def apply_shuffle_decision(state: dict, dealer_id: str,
                           cheated: bool,
                           chosen_hand: Optional[str] = None) -> dict:
    """
    Dealer commits their shuffle choice. Valid in SHUFFLE_PHASE only.
    chosen_hand must be a key from CHEAT_HAND_OPTIONS when cheated=True.
    """
    if state["phase"] != PHASE_SHUFFLE:
        raise ValueError(f"Not in shuffle phase (current: {state['phase']!r})")

    active     = [_get_player(state, pid) for pid in state["hand_active_ids"]]
    dealer_pos = state["dealer_pos"]
    dealer     = active[dealer_pos]

    if dealer["id"] != dealer_id:
        raise ValueError(f"{dealer_id!r} is not the dealer")

    if cheated and chosen_hand not in CHEAT_HANDS:
        raise ValueError(f"Unknown cheat hand {chosen_hand!r}")

    state["events"] = []

    n       = len(active)
    utg_pos = dealer_pos if n == 2 else (dealer_pos + 3) % n

    return _after_shuffle_decision(state, dealer, cheated, chosen_hand, utg_pos)


def apply_accusation(state: dict, player_id: str, accuses: bool) -> dict:
    """
    Record a human player's accusation decision. Valid in ACCUSATION_PHASE only.
    The player must be first in accusation_order.
    When all pending humans have decided, resolves and deals automatically.
    """
    if state["phase"] != PHASE_ACCUSATION:
        raise ValueError(f"Not in accusation phase (current: {state['phase']!r})")

    if not state["accusation_order"] or state["accusation_order"][0] != player_id:
        raise ValueError(f"Not {player_id!r}'s turn to accuse")

    state["events"] = []
    state["accusation_order"].pop(0)

    if accuses:
        cost = 2 * state["big_blind"]
        p    = _get_player(state, player_id)
        if p["chips"] < cost:
            raise ValueError(f"Insufficient chips to accuse (need {cost})")
        p["chips"]        -= cost
        state["accusers"]  = [player_id]
        _emit(state, "human_accused", accuser_id=player_id, cost=cost)
        return _resolve_and_deal(state)

    _emit(state, "passed_accusation", player_id=player_id)
    return _advance_accusation(state)


def apply_action(state: dict, player_id: str, action: str,
                 amount: int = 0,
                 use_ability_first: bool = False,
                 ability_target_id: Optional[str] = None) -> dict:
    """
    Apply a betting action for player_id.
    action: "fold" | "check" | "call" | "raise" | "all-in"
    When use_ability_first=True, the player's role ability fires before the bet.
    ability_target_id names the shoot/curse target (None = auto-pick).
    Auto-advances bots until the next human turn or phase end.
    """
    if state["phase"] not in BETTING_PHASES:
        raise ValueError(f"Not in a betting phase (current: {state['phase']!r})")

    if not state["to_act"] or state["to_act"][0] != player_id:
        raise ValueError(f"Not {player_id!r}'s turn to act")

    p = _get_player(state, player_id)
    if p is None:
        raise ValueError(f"Player {player_id!r} not found")

    state["events"] = []

    if use_ability_first:
        role = p.get("role")
        if role == "GUNNER":
            _do_shoot(state, p, ability_target_id)
        elif role == "CURSED" and not p.get("has_cursed"):
            _do_curse(state, p, ability_target_id)
        _fold_dead_players(state)
        if p["chips"] == 0:
            p["folded"] = True
            state["to_act"].pop(0)
            return _advance_betting(state)

    state["to_act"].pop(0)
    _do_action(state, p, action, amount)
    _fold_dead_players(state)
    return _advance_betting(state)


def apply_ability(state: dict, player_id: str,
                  ability_type: str,
                  target_id: Optional[str] = None) -> dict:
    """
    Use a role ability outside a betting action (e.g., between hands).
    ability_type: "shoot" | "curse"
    """
    p = _get_player(state, player_id)
    if p is None:
        raise ValueError(f"Player {player_id!r} not found")

    state["events"] = []

    if ability_type == "shoot" and p.get("role") == "GUNNER":
        _do_shoot(state, p, target_id)
    elif ability_type == "curse" and p.get("role") == "CURSED":
        _do_curse(state, p, target_id)
    else:
        raise ValueError(
            f"Player {player_id!r} cannot use ability {ability_type!r}")

    _fold_dead_players(state)
    return state
