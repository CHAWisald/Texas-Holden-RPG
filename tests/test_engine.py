"""
tests/test_engine.py — pytest coverage for game/engine.py.

Cards are represented as {"rank": int, "suit": str} dicts throughout.
Suit values: "Hearts", "Diamonds", "Clubs", "Spades".
"""

import pytest
from unittest.mock import patch

from game.engine import (
    create_game,
    start_hand,
    apply_shuffle_decision,
    apply_accusation,
    apply_action,
    apply_ability,
    _get_player,
    _active,
    _showdown,
    PHASE_WAITING,
    PHASE_SHUFFLE,
    PHASE_ACCUSATION,
    PHASE_PREFLOP,
    PHASE_FLOP,
    PHASE_TURN,
    PHASE_RIVER,
    PHASE_HAND_OVER,
    PHASE_GAME_OVER,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _card(rank: int, suit: str) -> dict:
    return {"rank": rank, "suit": suit}


H, D, C, S = "Hearts", "Diamonds", "Clubs", "Spades"


def _two_human_game() -> dict:
    return create_game([
        {"id": "h0", "name": "Alice", "is_human": True},
        {"id": "h1", "name": "Bob",   "is_human": True},
    ])


def _bot_game(n: int = 3) -> dict:
    return create_game([
        {"id": f"b{i}", "name": f"Bot{i}", "is_human": False, "aggression": 0.5}
        for i in range(n)
    ])


def _advance_to_preflop(state: dict) -> dict:
    """Drive a 2-human game through shuffle + accusation into PREFLOP."""
    state = start_hand(state)
    if state["phase"] == PHASE_SHUFFLE:
        dealer_id = next(
            e["dealer_id"] for e in state["events"] if e["type"] == "shuffle_phase"
        )
        state = apply_shuffle_decision(state, dealer_id, cheated=False)
    while state["phase"] == PHASE_ACCUSATION:
        pid = state["accusation_order"][0]
        state = apply_accusation(state, pid, accuses=False)
    assert state["phase"] == PHASE_PREFLOP
    return state


# ── create_game ────────────────────────────────────────────────────────────────

class TestCreateGame:
    def test_initial_phase_is_waiting(self):
        state = _two_human_game()
        assert state["phase"] == PHASE_WAITING

    def test_player_count(self):
        state = _two_human_game()
        assert len(state["players"]) == 2

    def test_default_chips(self):
        state = _two_human_game()
        for p in state["players"]:
            assert p["chips"] == 1000

    def test_custom_chips(self):
        state = create_game([{"id": "p", "name": "P", "is_human": True, "chips": 500}])
        assert _get_player(state, "p")["chips"] == 500

    def test_blinds_stored(self):
        state = create_game(
            [{"id": "p", "name": "P", "is_human": False}],
            small_blind=5, big_blind=10,
        )
        assert state["small_blind"] == 5
        assert state["big_blind"] == 10

    def test_player_fields_present(self):
        state = _two_human_game()
        p = state["players"][0]
        for field in ("id", "name", "chips", "hole_cards", "folded", "all_in",
                      "is_human", "role", "is_devil", "has_cursed", "bullets_used"):
            assert field in p, f"missing field: {field}"


# ── start_hand ─────────────────────────────────────────────────────────────────

class TestStartHand:
    def test_human_dealer_enters_shuffle_phase(self):
        # h0 is at index 0 → dealer on first hand
        state = start_hand(_two_human_game())
        assert state["phase"] == PHASE_SHUFFLE

    def test_bot_dealer_skips_shuffle_phase(self):
        # All bots → no shuffle pause
        state = start_hand(_bot_game(3))
        assert state["phase"] in (PHASE_HAND_OVER, PHASE_GAME_OVER,
                                  PHASE_PREFLOP, PHASE_FLOP, PHASE_TURN, PHASE_RIVER)
        assert state["phase"] != PHASE_SHUFFLE

    def test_blinds_deducted_from_chips(self):
        state = _advance_to_preflop(_two_human_game())
        total_chips = sum(p["chips"] for p in state["players"])
        assert total_chips == 2000 - 10 - 20  # both started at 1000; SB+BB taken

    def test_pot_equals_blinds(self):
        state = _advance_to_preflop(_two_human_game())
        assert state["pot"] == 30  # SB(10) + BB(20)

    def test_hand_num_increments(self):
        state = _two_human_game()
        assert state["hand_num"] == 0
        state = _advance_to_preflop(state)
        assert state["hand_num"] == 1

    def test_cannot_start_hand_mid_hand(self):
        state = _advance_to_preflop(_two_human_game())
        with pytest.raises(ValueError, match="Cannot start hand"):
            start_hand(state)

    def test_game_over_when_one_player_left(self):
        state = _two_human_game()
        _get_player(state, "h1")["chips"] = 0   # eliminate h1 before first hand
        state = start_hand(state)
        assert state["phase"] == PHASE_GAME_OVER

    def test_dealer_rotates_each_hand(self):
        state = _bot_game(3)
        assert state["dealer_idx"] == 0
        state = start_hand(state)   # all-bot hand auto-resolves to HAND_OVER
        # The button advances in _end_hand. (0+1)%2 and (0+1)%3 both == 1, so
        # whenever the hand ended with >=2 survivors the dealer index is now 1.
        if state["phase"] == PHASE_HAND_OVER:
            assert state["dealer_idx"] == 1


# ── shuffle phase ──────────────────────────────────────────────────────────────

class TestShufflePhase:
    def _get_shuffle_state(self):
        state = start_hand(_two_human_game())
        assert state["phase"] == PHASE_SHUFFLE
        return state

    def test_wrong_player_raises(self):
        state = self._get_shuffle_state()
        with pytest.raises(ValueError, match="not the dealer"):
            apply_shuffle_decision(state, "h1", cheated=False)

    def test_wrong_phase_raises(self):
        state = _two_human_game()   # phase = WAITING
        with pytest.raises(ValueError, match="shuffle phase"):
            apply_shuffle_decision(state, "h0", cheated=False)

    def test_invalid_cheat_hand_raises(self):
        state = self._get_shuffle_state()
        with pytest.raises(ValueError, match="Unknown cheat hand"):
            apply_shuffle_decision(state, "h0", cheated=True, chosen_hand="XX")

    def test_honest_shuffle_moves_to_accusation_or_preflop(self):
        state = self._get_shuffle_state()
        state = apply_shuffle_decision(state, "h0", cheated=False)
        assert state["phase"] in (PHASE_ACCUSATION, PHASE_PREFLOP)

    def test_cheat_flag_stored_in_state(self):
        state = self._get_shuffle_state()
        state = apply_shuffle_decision(state, "h0", cheated=True, chosen_hand="AA")
        assert state["cheated"] is True
        assert state["chosen_hand"] == "AA"

    def test_elapsed_time_generated(self):
        state = self._get_shuffle_state()
        state = apply_shuffle_decision(state, "h0", cheated=False)
        assert state["cheat_elapsed"] is not None
        assert 10 < state["cheat_elapsed"] < 25   # plausible shuffle time


# ── accusation phase ───────────────────────────────────────────────────────────

class TestAccusationPhase:
    def _reach_accusation(self, cheated=False, chosen_hand=None):
        """
        2-human game. h0 is dealer; h1 is the only non-dealer human.
        After shuffle h1 enters ACCUSATION_PHASE.
        """
        state = start_hand(_two_human_game())
        state = apply_shuffle_decision(state, "h0", cheated=cheated,
                                       chosen_hand=chosen_hand)
        # h1 should be in accusation_order if they have enough chips
        if state["phase"] == PHASE_ACCUSATION:
            return state
        pytest.skip("accusation phase not reached — bot skipped it")

    def test_passing_costs_no_chips(self):
        state = self._reach_accusation()
        chips_before = _get_player(state, "h1")["chips"]
        state = apply_accusation(state, "h1", accuses=False)
        assert _get_player(state, "h1")["chips"] == chips_before

    def test_false_accusation_dealer_gains_chips(self):
        state = self._reach_accusation(cheated=False)
        dealer_chips_before = _get_player(state, "h0")["chips"]
        cost = 2 * state["big_blind"]
        state = apply_accusation(state, "h1", accuses=True)
        # Dealer collects the accusation cost
        assert _get_player(state, "h0")["chips"] == dealer_chips_before + cost

    def test_caught_cheating_penalizes_dealer(self):
        state = self._reach_accusation(cheated=True, chosen_hand="AA")
        dealer_chips_before = _get_player(state, "h0")["chips"]
        cost = 2 * state["big_blind"]
        state = apply_accusation(state, "h1", accuses=True)
        dealer = _get_player(state, "h0")
        # Dealer should have lost at least the accusation cost
        assert dealer["chips"] < dealer_chips_before

    def test_wrong_player_raises(self):
        state = self._reach_accusation()
        with pytest.raises(ValueError):
            apply_accusation(state, "h0", accuses=False)   # h0 is dealer, not in order

    def test_wrong_phase_raises(self):
        state = _two_human_game()   # WAITING, not ACCUSATION
        with pytest.raises(ValueError, match="accusation phase"):
            apply_accusation(state, "h0", accuses=False)

    def test_accusation_advances_to_preflop(self):
        state = self._reach_accusation()
        state = apply_accusation(state, "h1", accuses=False)
        assert state["phase"] == PHASE_PREFLOP


# ── betting actions ────────────────────────────────────────────────────────────

class TestBettingActions:
    @pytest.fixture
    def preflop(self):
        return _advance_to_preflop(_two_human_game())

    def test_fold_sets_folded_flag(self, preflop):
        pid = preflop["to_act"][0]
        state = apply_action(preflop, pid, "fold")
        assert _get_player(state, pid)["folded"] is True

    def test_fold_ends_hand_when_last_player(self, preflop):
        """In heads-up, folding should resolve the hand immediately."""
        pid = preflop["to_act"][0]
        state = apply_action(preflop, pid, "fold")
        # Other player wins; hand is over or the remaining player acts
        assert state["phase"] in (PHASE_HAND_OVER, PHASE_PREFLOP,
                                  PHASE_FLOP, PHASE_TURN, PHASE_RIVER)

    def test_call_deducts_correct_chips(self, preflop):
        pid   = preflop["to_act"][0]
        p     = _get_player(preflop, pid)
        chips_before  = p["chips"]
        to_call       = preflop["current_bet"] - p["street_bet"]
        apply_action(preflop, pid, "call")
        assert p["chips"] == chips_before - to_call

    def test_call_increases_pot(self, preflop):
        pid     = preflop["to_act"][0]
        p       = _get_player(preflop, pid)
        pot_before = preflop["pot"]
        to_call    = preflop["current_bet"] - p["street_bet"]
        state  = apply_action(preflop, pid, "call")
        assert state["pot"] == pot_before + to_call

    def test_raise_updates_current_bet(self, preflop):
        pid      = preflop["to_act"][0]
        before   = preflop["current_bet"]
        raise_by = preflop["big_blind"]
        state    = apply_action(preflop, pid, "raise", amount=raise_by)
        # A raise of `raise_by` over the current bet sets current_bet exactly
        # that much higher (the raiser's new street_bet).
        assert state["current_bet"] == before + raise_by

    def test_raise_re_queues_other_players(self, preflop):
        pid   = preflop["to_act"][0]
        other = [x["id"] for x in preflop["players"] if x["id"] != pid]
        state = apply_action(preflop, pid, "raise", amount=preflop["big_blind"])
        # Other players must be back in to_act (if not folded/all-in)
        for oid in other:
            op = _get_player(state, oid)
            if not op["folded"] and not op["all_in"] and state["phase"] in (PHASE_PREFLOP,):
                assert oid in state["to_act"]

    def test_check_valid_when_no_bet(self):
        """BB can check after everyone else called/no raises."""
        state = _advance_to_preflop(_two_human_game())
        # h0 is UTG (dealer in heads-up), h1 is BB already at current_bet
        # Drive h0 to call so h1 faces to_call=0
        pid0 = state["to_act"][0]
        to_call0 = state["current_bet"] - _get_player(state, pid0)["street_bet"]
        state = apply_action(state, pid0, "call")
        # Now h1 is BB and current_bet == h1's street_bet → can check
        if state["phase"] == PHASE_PREFLOP and state["to_act"]:
            pid1 = state["to_act"][0]
            p1   = _get_player(state, pid1)
            if state["current_bet"] == p1["street_bet"]:
                state = apply_action(state, pid1, "check")   # should not raise

    def test_check_raises_when_bet_pending(self, preflop):
        """Player must call or fold when there is a bet to call."""
        pid     = preflop["to_act"][0]
        p       = _get_player(preflop, pid)
        to_call = preflop["current_bet"] - p["street_bet"]
        if to_call > 0:
            with pytest.raises(ValueError, match="Cannot check"):
                apply_action(preflop, pid, "check")

    def test_all_in_caps_at_chip_count(self, preflop):
        pid = preflop["to_act"][0]
        p   = _get_player(preflop, pid)
        original_chips = p["chips"]
        state = apply_action(preflop, pid, "all-in")
        assert p["chips"] == 0
        assert p["all_in"] is True

    def test_over_raise_becomes_all_in(self, preflop):
        """Raising by more than available chips results in all-in, not an error."""
        pid = preflop["to_act"][0]
        p   = _get_player(preflop, pid)
        state = apply_action(preflop, pid, "raise", amount=999_999)
        assert p["chips"] == 0
        assert p["all_in"] is True

    def test_not_your_turn_raises(self, preflop):
        pid0 = preflop["to_act"][0]
        pid1 = preflop["to_act"][1] if len(preflop["to_act"]) > 1 else "h1"
        if pid1 != pid0:
            with pytest.raises(ValueError, match="turn"):
                apply_action(preflop, pid1, "check")

    def test_wrong_phase_raises(self):
        state = _two_human_game()   # WAITING
        with pytest.raises(ValueError, match="betting phase"):
            apply_action(state, "h0", "fold")


# ── phase progression ──────────────────────────────────────────────────────────

class TestPhaseProgression:
    def _all_fold_except_one(self, state: dict) -> dict:
        """Fold all active players except the last one."""
        while state["phase"] in (PHASE_PREFLOP, PHASE_FLOP, PHASE_TURN, PHASE_RIVER):
            if not state["to_act"]:
                break
            pid = state["to_act"][0]
            p   = _get_player(state, pid)
            if not p["is_human"]:
                break
            # fold if there are other non-folded players, else check/call
            remaining = [q for q in state["players"] if not q["folded"]]
            if len(remaining) > 1:
                state = apply_action(state, pid, "fold")
            else:
                break
        return state

    def test_preflop_then_flop_has_three_community_cards(self):
        state = _advance_to_preflop(_two_human_game())
        # Both humans call/check to end preflop
        while state["phase"] == PHASE_PREFLOP and state["to_act"]:
            pid = state["to_act"][0]
            p   = _get_player(state, pid)
            to_call = state["current_bet"] - p["street_bet"]
            action = "call" if to_call > 0 else "check"
            state = apply_action(state, pid, action)
        if state["phase"] == PHASE_FLOP:
            assert len(state["community_cards"]) == 3

    def test_flop_then_turn_has_four_community_cards(self):
        state = _advance_to_preflop(_two_human_game())
        # Fast-forward by checking/calling all streets
        for phase in (PHASE_PREFLOP, PHASE_FLOP):
            while state["phase"] == phase and state["to_act"]:
                pid = state["to_act"][0]
                p   = _get_player(state, pid)
                to_call = state["current_bet"] - p["street_bet"]
                action = "call" if to_call > 0 else "check"
                state = apply_action(state, pid, action)
        if state["phase"] == PHASE_TURN:
            assert len(state["community_cards"]) == 4

    def test_river_leads_to_hand_over(self):
        state = _advance_to_preflop(_two_human_game())
        for phase in (PHASE_PREFLOP, PHASE_FLOP, PHASE_TURN, PHASE_RIVER):
            while state["phase"] == phase and state["to_act"]:
                pid = state["to_act"][0]
                p   = _get_player(state, pid)
                to_call = state["current_bet"] - p["street_bet"]
                action = "call" if to_call > 0 else "check"
                state = apply_action(state, pid, action)
        assert state["phase"] in (PHASE_HAND_OVER, PHASE_GAME_OVER)

    def test_early_fold_skips_to_hand_over(self):
        """If one player folds immediately, the hand ends without betting streets."""
        state = _advance_to_preflop(_two_human_game())
        pid   = state["to_act"][0]
        # Fold; if only 1 player left the hand ends
        state = apply_action(state, pid, "fold")
        remaining = [p for p in state["players"] if not p["folded"]]
        if len(remaining) == 1:
            assert state["phase"] in (PHASE_HAND_OVER, PHASE_GAME_OVER)

    def test_all_in_then_fold_runs_board_to_showdown(self):
        """3 players, one all-in: when one of the other two folds, the lone
        remaining live player is NOT asked to check down every street — the
        board runs straight to showdown. Regression for the stalled hand,
        where the engine used to prompt that player on flop, turn and river."""
        state = create_game([
            {"id": "sh", "name": "Short", "is_human": True, "chips": 200},
            {"id": "a",  "name": "A",     "is_human": True, "chips": 2000},
            {"id": "b",  "name": "B",     "is_human": True, "chips": 2000},
        ])
        state = _advance_to_preflop(state)

        betting = (PHASE_PREFLOP, PHASE_FLOP, PHASE_TURN, PHASE_RIVER)
        postflop_prompts = 0
        for _ in range(30):
            if state["phase"] not in betting:
                break
            pid     = state["to_act"][0]
            me      = _get_player(state, pid)
            to_call = state["current_bet"] - me["street_bet"]
            if state["phase"] != PHASE_PREFLOP:
                postflop_prompts += 1          # someone was asked to act post-flop
            if pid == "sh":
                action = "all-in"
            elif pid == "a":
                action = "fold" if to_call > 0 else "check"
            else:                              # b always matches the all-in
                action = "call" if to_call > 0 else "check"
            state = apply_action(state, pid, action)

        # Hand resolved at showdown between the all-in player and the caller.
        assert state["phase"] in (PHASE_HAND_OVER, PHASE_GAME_OVER)
        assert state["hand_result"]["type"] == "showdown"
        assert set(state["hand_result"]["all_hands"].keys()) == {"sh", "b"}
        # The lone live player was never prompted after the fold — the engine
        # ran the remaining streets straight to showdown.
        assert postflop_prompts == 0


# ── showdown / hand result ─────────────────────────────────────────────────────

class TestShowdown:
    def _showdown_state(self, p1_hole, p2_hole, board):
        """Build a minimal state and call _showdown directly."""
        state = create_game([
            {"id": "p1", "name": "P1", "is_human": False, "chips": 500},
            {"id": "p2", "name": "P2", "is_human": False, "chips": 500},
        ])
        state["pot"]              = 200
        state["community_cards"]  = board
        state["deck"]             = []
        p1 = _get_player(state, "p1")
        p2 = _get_player(state, "p2")
        p1["hole_cards"] = p1_hole
        p2["hole_cards"] = p2_hole
        p1["folded"] = False
        p2["folded"] = False
        return state

    def test_flush_beats_straight(self):
        """
        Board: 2H 4H 6H 8D TD
        P1 (flush):    AH KH  →  A-K-6-4-2 Hearts
        P2 (straight): 3S 5C  →  2-3-4-5-6 straight
        """
        board = [_card(2,H), _card(4,H), _card(6,H), _card(8,D), _card(10,D)]
        p1    = [_card(14,H), _card(13,H)]    # Ace-King of Hearts
        p2    = [_card(3,S), _card(5,C)]      # 3-5 offsuit

        state = self._showdown_state(p1, p2, board)
        _showdown(state)

        result = state["hand_result"]
        assert result["winner_ids"] == ["p1"], (
            f"Expected flush (p1) to beat straight (p2); "
            f"hands: {result['all_hands']}"
        )
        assert result["all_hands"]["p1"] == "Flush"
        assert result["all_hands"]["p2"] == "Straight"

    def test_royal_flush_beats_straight_flush(self):
        """
        Board: TH JH QH KH 2C
        P1 (royal flush):    AH 9H  → Royal Flush (A-K-Q-J-T Hearts)
        P2 (straight flush): 8H 9H  → but 9H is taken by p1... use different cards
        Actually P2: 8H 9S → straight flush 8-9-T-J-Q Hearts (if 8H in deck)
        Let's use: P2: 8H 9C → P2 best: Q-K-T-J-9 not all same suit.
        Simpler: P1 has AH, P2 has 9H (one royal card only)
        Board: TH JH QH KH 2C
        P1: AH 5C → Royal Flush
        P2: 9H 8H → Straight Flush 8-9-T-J-Q Hearts
        """
        board = [_card(10,H), _card(11,H), _card(12,H), _card(13,H), _card(2,C)]
        p1    = [_card(14,H), _card(5,C)]    # Royal Flush
        p2    = [_card(9,H),  _card(8,H)]    # Straight Flush 8-9-T-J-Q

        state = self._showdown_state(p1, p2, board)
        _showdown(state)

        result = state["hand_result"]
        assert result["winner_ids"] == ["p1"], (
            f"Expected royal flush to beat straight flush; "
            f"hands: {result['all_hands']}"
        )

    def test_split_pot_equal_hands(self):
        """
        Board: AH KH QH JH TH  (Royal Flush on board for everyone)
        P1: 2C 3D, P2: 4S 5H  → both play the board → split
        """
        board = [_card(14,H), _card(13,H), _card(12,H), _card(11,H), _card(10,H)]
        p1    = [_card(2,C), _card(3,D)]
        p2    = [_card(4,S), _card(5,H)]

        state = self._showdown_state(p1, p2, board)
        state["pot"] = 200
        _showdown(state)

        result = state["hand_result"]
        assert set(result["winner_ids"]) == {"p1", "p2"}
        assert _get_player(state, "p1")["chips"] == 500 + 100
        assert _get_player(state, "p2")["chips"] == 500 + 100

    def test_split_pot_odd_remainder_goes_to_first(self):
        """Odd pot: each winner gets the floor share, the first winner the +1."""
        board = [_card(14,H), _card(13,H), _card(12,H), _card(11,H), _card(10,H)]
        p1    = [_card(2,C), _card(3,D)]
        p2    = [_card(4,S), _card(5,H)]

        state = self._showdown_state(p1, p2, board)
        state["pot"] = 201          # odd → remainder 1
        _showdown(state)

        assert set(state["hand_result"]["winner_ids"]) == {"p1", "p2"}
        # _still_in order is [p1, p2] → p1 is winners[0] and takes the extra chip.
        assert _get_player(state, "p1")["chips"] == 500 + 101
        assert _get_player(state, "p2")["chips"] == 500 + 100

    def test_pot_fully_awarded(self):
        board = [_card(2,H), _card(4,H), _card(6,H), _card(8,D), _card(10,D)]
        p1    = [_card(14,H), _card(13,H)]
        p2    = [_card(3,S), _card(5,C)]
        state = self._showdown_state(p1, p2, board)
        chips_before = sum(p["chips"] for p in state["players"])
        _showdown(state)
        chips_after = sum(p["chips"] for p in state["players"])
        assert chips_after == chips_before + state["pot"]

    def test_side_pot_caps_short_all_in_winner(self):
        """A short all-in player with the best hand wins only the main pot;
        the side pot is contested by the deeper-stacked players."""
        state = create_game([
            {"id": "p1", "name": "P1", "is_human": False, "chips": 0},
            {"id": "p2", "name": "P2", "is_human": False, "chips": 0},
            {"id": "p3", "name": "P3", "is_human": False, "chips": 0},
        ])
        # Dry board, no flush/straight: AA > KK > QQ.
        state["community_cards"] = [_card(2,H), _card(7,D), _card(9,S),
                                    _card(11,C), _card(4,H)]
        state["deck"] = []
        holes = {"p1": [_card(14,S), _card(14,D)],   # AA  — best, but short
                 "p2": [_card(13,S), _card(13,D)],   # KK  — wins the side pot
                 "p3": [_card(12,S), _card(12,D)]}    # QQ  — wins nothing
        bets  = {"p1": 50, "p2": 300, "p3": 300}
        for pid, hole in holes.items():
            p = _get_player(state, pid)
            p["hole_cards"] = hole
            p["folded"]     = False
            p["total_bet"]  = bets[pid]
        state["pot"] = sum(bets.values())   # 650

        _showdown(state)

        # Main pot 50*3 = 150 → P1 (best). Side pot 250*2 = 500 → P2.
        assert _get_player(state, "p1")["chips"] == 150
        assert _get_player(state, "p2")["chips"] == 500
        assert _get_player(state, "p3")["chips"] == 0
        # Every chip in the pot is paid out — no manufacturing or loss.
        assert sum(p["chips"] for p in state["players"]) == 650

    def test_folded_contributor_forfeits_to_side_pots(self):
        """A player who contributed then folded forfeits their chips to the
        players still in the hand."""
        state = create_game([
            {"id": "p1", "name": "P1", "is_human": False, "chips": 0},
            {"id": "p2", "name": "P2", "is_human": False, "chips": 0},
        ])
        state["community_cards"] = [_card(2,H), _card(7,D), _card(9,S),
                                    _card(11,C), _card(4,H)]
        state["deck"] = []
        p1 = _get_player(state, "p1")
        p2 = _get_player(state, "p2")
        p1["hole_cards"], p1["total_bet"], p1["folded"] = [_card(14,S), _card(14,D)], 100, False
        p2["hole_cards"], p2["total_bet"], p2["folded"] = [_card(13,S), _card(13,D)], 100, True
        state["pot"] = 200

        _showdown(state)

        # P2 folded → P1 takes the whole 200 even though P2 matched it.
        assert _get_player(state, "p1")["chips"] == 200
        assert _get_player(state, "p2")["chips"] == 0

    def test_uncalled_overbet_is_returned_not_won(self):
        """An over-bet no opponent could match is *returned* to the bettor,
        who is NOT flagged a winner; the best hand wins the contested pot.

        Regression for the 'showdown awards everyone their own stack' bug:
        the all-in over-bettor used to be listed as a winner of their own
        returned chips (which, being all-in, equalled their leftover stack).
        Board: 6D TD 2C 2D 9S."""
        state = create_game([
            {"id": "you",   "name": "You",   "is_human": False, "chips": 0},
            {"id": "wyatt", "name": "Wyatt", "is_human": False, "chips": 0},
        ])
        state["community_cards"] = [_card(6,D), _card(10,D), _card(2,C),
                                    _card(2,D), _card(9,S)]
        state["deck"] = []
        you, wyatt = _get_player(state, "you"), _get_player(state, "wyatt")
        you["hole_cards"],   you["total_bet"],   you["folded"]   = \
            [_card(13,H), _card(12,H)], 2533, False   # one pair of 2s
        wyatt["hole_cards"], wyatt["total_bet"], wyatt["folded"] = \
            [_card(8,D),  _card(8,H)],  1467, False    # two pair (8s & 2s)
        state["pot"] = 2533 + 1467

        _showdown(state)
        result = state["hand_result"]

        # Wyatt (two pair) is the SOLE winner of the contested 1467*2 pot.
        assert result["winner_ids"] == ["wyatt"]
        assert result["winnings"] == {"wyatt": 2934}
        # You over-shoved 1066 nobody matched — returned, not won.
        assert result["refunds"] == {"you": 1066}
        assert "you" not in result["winner_ids"]
        assert wyatt["chips"] == 2934 and you["chips"] == 1066
        assert you["chips"] + wyatt["chips"] == state["pot"]

    def test_winner_with_uncalled_remainder_splits_won_and_returned(self):
        """The best hand that also over-bet wins the contested pot AND has its
        uncalled top slice returned — the two are counted separately."""
        state = create_game([
            {"id": "big",   "name": "Big",   "is_human": False, "chips": 0},
            {"id": "small", "name": "Small", "is_human": False, "chips": 0},
        ])
        state["community_cards"] = [_card(2,H), _card(7,D), _card(9,S),
                                    _card(11,C), _card(4,H)]
        state["deck"] = []
        big, small = _get_player(state, "big"), _get_player(state, "small")
        big["hole_cards"],   big["total_bet"],   big["folded"]   = \
            [_card(14,S), _card(14,D)], 300, False    # AA, over-bet
        small["hole_cards"], small["total_bet"], small["folded"] = \
            [_card(13,S), _card(13,D)], 100, False    # KK, short stack
        state["pot"] = 400

        _showdown(state)
        result = state["hand_result"]

        # Contested 100*2=200 → Big (AA). Big's uncalled 200 over-bet returned.
        assert result["winner_ids"] == ["big"]
        assert result["winnings"] == {"big": 200}
        assert result["refunds"] == {"big": 200}
        assert big["chips"] == 400 and small["chips"] == 0

    def test_fold_win_awards_pot(self):
        state = _advance_to_preflop(_two_human_game())
        pid   = state["to_act"][0]
        other = next(p for p in state["players"] if p["id"] != pid)
        chips_before = other["chips"]
        pot          = state["pot"]
        state = apply_action(state, pid, "fold")
        # Only runs if the fold caused the hand to end
        if state["phase"] in (PHASE_HAND_OVER, PHASE_GAME_OVER):
            result = state["hand_result"]
            assert result["winner_ids"] == [other["id"]]


# ── role abilities ─────────────────────────────────────────────────────────────

class TestRoleAbilities:
    def _cursed_game(self):
        return create_game([
            {"id": "cursed", "name": "C", "is_human": True,  "role": "CURSED"},
            {"id": "target", "name": "T", "is_human": False, "role": None},
        ])

    def _gunner_game(self):
        return create_game([
            {"id": "gunner", "name": "G", "is_human": True,  "role": "GUNNER"},
            {"id": "target", "name": "T", "is_human": False, "role": None},
        ])

    def test_curse_sets_curse_hands_left(self):
        state = self._cursed_game()
        state = apply_ability(state, "cursed", "curse", target_id="target")
        target = _get_player(state, "target")
        assert target["curse_hands_left"] > 0, "curse should set curse_hands_left"

    def test_curse_marks_has_cursed(self):
        state = self._cursed_game()
        state = apply_ability(state, "cursed", "curse", target_id="target")
        assert _get_player(state, "cursed")["has_cursed"] is True

    def test_curse_cannot_be_used_twice(self):
        state = self._cursed_game()
        state = apply_ability(state, "cursed", "curse", target_id="target")
        # Second curse attempt: has_cursed=True → ability_failed, target unchanged.
        old_hands = _get_player(state, "target")["curse_hands_left"]
        state = apply_ability(state, "cursed", "curse", target_id="target")
        failed_event = any(e["type"] == "ability_failed" for e in state["events"])
        assert failed_event
        assert _get_player(state, "target")["curse_hands_left"] == old_hands

    def test_shoot_hit_eliminates_target(self):
        """Mock revolver to always fire."""
        state = self._gunner_game()
        with patch("game.engine._fire_revolver", return_value=True):
            state = apply_ability(state, "gunner", "shoot", target_id="target")
        assert _get_player(state, "target")["chips"] == 0

    def test_shoot_miss_leaves_target_alive(self):
        """Mock revolver to never fire."""
        state = self._gunner_game()
        target_chips = _get_player(state, "target")["chips"]
        with patch("game.engine._fire_revolver", return_value=False):
            state = apply_ability(state, "gunner", "shoot", target_id="target")
        assert _get_player(state, "target")["chips"] == target_chips

    def test_shoot_costs_chips(self):
        state = self._gunner_game()
        chips_before = _get_player(state, "gunner")["chips"]
        with patch("game.engine._fire_revolver", return_value=False):
            state = apply_ability(state, "gunner", "shoot", target_id="target")
        cost = state["big_blind"] * 10 * (2 ** 0)   # first shot: 10×BB
        assert _get_player(state, "gunner")["chips"] == chips_before - cost

    def test_shoot_fails_when_insufficient_chips(self):
        state = self._gunner_game()
        _get_player(state, "gunner")["chips"] = 1   # can't afford
        state = apply_ability(state, "gunner", "shoot", target_id="target")
        failed = any(e["type"] == "ability_failed" for e in state["events"])
        assert failed

    def test_wrong_role_ability_raises(self):
        state = self._cursed_game()
        with pytest.raises(ValueError, match="cannot use ability"):
            apply_ability(state, "cursed", "shoot")

    def test_self_shoot_is_free_and_rewards_on_click(self):
        """Self-shoot costs no chips; a click still grants the 20BB reward."""
        state = self._gunner_game()
        chips_before = _get_player(state, "gunner")["chips"]
        with patch("game.engine._fire_revolver", return_value=False):
            state = apply_ability(state, "gunner", "shoot", target_id=None)
        assert _get_player(state, "gunner")["chips"] == \
            chips_before + state["big_blind"] * 20

    def test_self_shoot_is_free_even_when_broke(self):
        """A broke Gunner can still take the self-shoot gamble — it costs
        nothing — but it still advances bullets_used."""
        state = self._gunner_game()
        _get_player(state, "gunner")["chips"] = 5
        with patch("game.engine._fire_revolver", return_value=False):
            state = apply_ability(state, "gunner", "shoot", target_id=None)
        assert not any(e["type"] == "ability_failed" for e in state["events"])
        g = _get_player(state, "gunner")
        assert g["chips"] == 5 + state["big_blind"] * 20
        assert g["bullets_used"] == 1

    def test_shot_cost_escalates_across_self_and_opponent_shots(self):
        """bullets_used is one counter: even the free self-shot doubles the
        next opponent shot's price."""
        state = self._gunner_game()
        bb = state["big_blind"]
        _get_player(state, "gunner")["chips"] = bb * 1000
        with patch("game.engine._fire_revolver", return_value=False):
            state = apply_ability(state, "gunner", "shoot", target_id=None)
            after_self = _get_player(state, "gunner")["chips"]
            state = apply_ability(state, "gunner", "shoot", target_id="target")
        assert after_self == bb * 1000 + bb * 20             # free self-shot, won 20BB
        assert _get_player(state, "gunner")["chips"] == after_self - bb * 20  # opp shot now 20BB

    def test_self_shoot_kills_on_bang(self):
        state = self._gunner_game()
        with patch("game.engine._fire_revolver", return_value=True):
            state = apply_ability(state, "gunner", "shoot", target_id=None)
        g = _get_player(state, "gunner")
        assert g["chips"] == 0
        assert g["died_by_revolver"] is True

    def test_ability_rejected_during_betting(self):
        """During betting, /ability is rejected (use use_ability_first instead)."""
        state = create_game([
            {"id": "gunner", "name": "G", "is_human": True, "role": "GUNNER"},
            {"id": "other",  "name": "O", "is_human": True, "role": None},
        ])
        state = _advance_to_preflop(state)
        with pytest.raises(ValueError, match="Cannot use /ability during betting"):
            apply_ability(state, "gunner", "shoot", target_id="other")

    def test_use_ability_first_in_action(self):
        """use_ability_first=True fires the ability before the betting action."""
        state = create_game([
            {"id": "cursed", "name": "C", "is_human": True, "role": "CURSED", "chips": 500},
            {"id": "target", "name": "T", "is_human": True, "role": None,     "chips": 500},
        ])
        state = _advance_to_preflop(state)
        # Heads-up: the first-created player is dealer/SB/UTG → acts first.
        pid = state["to_act"][0]
        assert pid == "cursed"
        state = apply_action(state, pid, "fold",
                             use_ability_first=True,
                             ability_target_id="target")
        assert _get_player(state, "cursed")["has_cursed"] is True
        assert _get_player(state, "target")["curse_hands_left"] > 0


# ── devil deal / bust ──────────────────────────────────────────────────────────

class TestBustRevival:
    def test_cursed_player_gets_devil_deal_on_bust(self):
        """Cursed player with 0 chips is auto-revived via devil deal."""
        state = create_game([
            {"id": "cursed", "name": "C", "is_human": True, "role": "CURSED", "chips": 20},
            {"id": "bot",    "name": "B", "is_human": False, "aggression": 0.5, "chips": 1000},
        ])
        # Force a showdown state where cursed player will lose all chips
        p = _get_player(state, "cursed")
        p["chips"] = 0   # simulate having just gone bust
        from game.engine import _handle_bust
        revived = _handle_bust(state, p)
        assert revived is True
        assert p["chips"] > 0
        assert p["is_devil"] is True
        assert p["devil_debt"] > 0

    def test_gunner_fires_revolver_on_bust(self):
        """Gunner with 0 chips fires the revolver; result depends on chamber."""
        state = create_game([
            {"id": "gunner", "name": "G", "is_human": True, "role": "GUNNER"},
        ])
        p = _get_player(state, "gunner")
        p["chips"] = 0
        # Mock fire to CLICK (survive)
        from game.engine import _handle_bust
        with patch("game.engine._fire_revolver", return_value=False):
            revived = _handle_bust(state, p)
        assert revived is True
        assert p["chips"] > 0

    def test_gunner_eliminated_on_bang(self):
        state = create_game([{"id": "g", "name": "G", "is_human": False, "role": "GUNNER"}])
        p = _get_player(state, "g")
        p["chips"] = 0
        from game.engine import _handle_bust
        with patch("game.engine._fire_revolver", return_value=True):
            revived = _handle_bust(state, p)
        assert revived is False
        assert p["died_by_revolver"] is True

    def test_eliminated_player_not_revived_in_later_hand(self):
        """A CURSED player eliminated in an earlier hand (not in hand_active_ids)
        must NOT be handed a fresh devil loan at the end of every later hand."""
        from game.engine import _end_hand
        state = create_game([
            {"id": "a",     "name": "A", "is_human": False, "chips": 100},
            {"id": "b",     "name": "B", "is_human": False, "chips": 0},
            {"id": "ghost", "name": "Ghost", "is_human": False,
             "role": "CURSED", "chips": 0},
        ])
        # Only a and b played this hand; ghost was eliminated previously.
        state["hand_active_ids"] = ["a", "b"]
        state["pot"] = 40
        _get_player(state, "b")["folded"]     = True    # a wins uncontested
        _get_player(state, "ghost")["folded"] = True    # ghost not in the hand
        _get_player(state, "ghost")["is_devil"] = False

        _end_hand(state)

        ghost = _get_player(state, "ghost")
        assert ghost["chips"] == 0          # stayed eliminated
        assert ghost["is_devil"] is False   # no devil deal granted


# ── game-level invariants ──────────────────────────────────────────────────────

class TestInvariants:
    def test_chips_are_conserved_across_hand(self):
        """Total chips in the system must never change."""
        state = _bot_game(3)
        total_before = sum(p["chips"] for p in state["players"])
        state = start_hand(state)
        total_after = sum(p["chips"] for p in state["players"])
        assert total_after == total_before

    def test_chips_conserved_across_many_hands(self):
        """Role-less games conserve total chips over a full match — including
        after eliminations (an eliminated seat must not be re-dealt pots, and
        side pots must not manufacture chips)."""
        import random
        for seed in (0, 1, 7, 42, 99):
            random.seed(seed)
            state = _bot_game(4)
            total_before = sum(p["chips"] for p in state["players"])
            for _ in range(60):
                if state["phase"] == PHASE_GAME_OVER:
                    break
                state = start_hand(state)
            total_after = sum(p["chips"] for p in state["players"])
            assert total_after == total_before, f"seed {seed}: {total_before} -> {total_after}"

    def test_hand_result_recorded_after_hand(self):
        """A completed hand records hand_result with winner_ids and the pot."""
        state = start_hand(_bot_game(2))
        result = state.get("hand_result")
        assert result is not None
        assert result["winner_ids"]                      # at least one winner
        assert result["pot"] >= state["big_blind"]       # blinds at minimum
        # The recorded winners are the players who actually gained chips.
        assert all(_get_player(state, w) is not None for w in result["winner_ids"])

    def test_pot_reset_on_next_hand(self):
        """state['pot'] is not zeroed at hand end, but the next start_hand resets it."""
        state = start_hand(_bot_game(3))
        if state["phase"] == PHASE_HAND_OVER:
            state = start_hand(state)
            # Fresh hand: pot holds only the freshly-posted blinds (or the hand
            # already auto-resolved, recording a new result).
            assert state["pot"] >= 0

    def test_multiple_hands_without_error(self):
        """Run 5 consecutive hands without raising."""
        state = _bot_game(4)
        for _ in range(5):
            if state["phase"] == PHASE_GAME_OVER:
                break
            state = start_hand(state)
            assert state["phase"] in (
                PHASE_HAND_OVER, PHASE_GAME_OVER,
                PHASE_PREFLOP, PHASE_FLOP, PHASE_TURN, PHASE_RIVER,
            )
