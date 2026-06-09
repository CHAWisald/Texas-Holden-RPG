"""
Tests for HandEvaluator — every hand rank plus tiebreaker and 7-card edge cases.
"""
import pytest
from game.card import Card, Suit
from game.hand_evaluator import HandEvaluator


# ── helpers ───────────────────────────────────────────────────────────────────

def c(rank: int, suit: str) -> Card:
    """Shorthand: c(14,'s') → Ace of Spades."""
    s = {'h': Suit.HEARTS, 'd': Suit.DIAMONDS, 'c': Suit.CLUBS, 's': Suit.SPADES}
    return Card(rank, s[suit])


def score(cards):
    return HandEvaluator.best_hand(cards)[0]


def name(cards):
    return HandEvaluator.best_hand(cards)[1]


# ── fewer than 5 cards ────────────────────────────────────────────────────────

class TestInsufficientCards:
    def test_none_on_four_cards(self):
        cards = [c(14,'s'), c(13,'s'), c(12,'s'), c(11,'s')]
        assert HandEvaluator.best_hand(cards) is None

    def test_none_on_empty(self):
        assert HandEvaluator.best_hand([]) is None


# ── straight-flush & royal flush ─────────────────────────────────────────────

class TestStraightFlushRoyalFlush:
    def test_royal_flush(self):
        cards = [c(14,'s'), c(13,'s'), c(12,'s'), c(11,'s'), c(10,'s')]
        assert name(cards) == 'Royal Flush'
        assert score(cards)[0] == 10

    def test_royal_flush_score_tuple(self):
        cards = [c(14,'h'), c(13,'h'), c(12,'h'), c(11,'h'), c(10,'h')]
        assert score(cards) == (10, (14, 13, 12, 11, 10))

    def test_straight_flush_nine_high(self):
        cards = [c(9,'d'), c(8,'d'), c(7,'d'), c(6,'d'), c(5,'d')]
        assert name(cards) == 'Straight Flush'
        assert score(cards) == (9, (9, 8, 7, 6, 5))

    def test_straight_flush_king_high(self):
        cards = [c(13,'c'), c(12,'c'), c(11,'c'), c(10,'c'), c(9,'c')]
        assert name(cards) == 'Straight Flush'
        assert score(cards)[0] == 9

    def test_steel_wheel_is_straight_flush_not_royal(self):
        # A-2-3-4-5 suited = steel wheel = 5-high straight flush
        cards = [c(14,'h'), c(5,'h'), c(4,'h'), c(3,'h'), c(2,'h')]
        assert name(cards) == 'Straight Flush'
        assert score(cards)[0] == 9
        assert score(cards)[1][0] == 5   # effective high card is 5, not 14

    def test_royal_beats_straight_flush(self):
        royal = [c(14,'s'), c(13,'s'), c(12,'s'), c(11,'s'), c(10,'s')]
        sf    = [c(9,'d'),  c(8,'d'),  c(7,'d'),  c(6,'d'),  c(5,'d')]
        assert score(royal) > score(sf)

    def test_higher_straight_flush_wins(self):
        hi = [c(9,'c'), c(8,'c'), c(7,'c'), c(6,'c'), c(5,'c')]
        lo = [c(8,'h'), c(7,'h'), c(6,'h'), c(5,'h'), c(4,'h')]
        assert score(hi) > score(lo)

    def test_7card_picks_royal_flush(self):
        # Community gives A♠ K♠ Q♠ J♠ T♠; hole cards are junk
        cards = [c(14,'s'), c(13,'s'), c(12,'s'), c(11,'s'), c(10,'s'),
                 c(2,'h'), c(3,'d')]
        assert name(cards) == 'Royal Flush'


# ── four of a kind ────────────────────────────────────────────────────────────

class TestFourOfAKind:
    def test_basic(self):
        cards = [c(14,'s'), c(14,'h'), c(14,'d'), c(14,'c'), c(13,'s')]
        assert name(cards) == 'Four of a Kind'
        assert score(cards)[0] == 8

    def test_quad_rank_first_in_tuple(self):
        cards = [c(7,'s'), c(7,'h'), c(7,'d'), c(7,'c'), c(2,'s')]
        s = score(cards)
        assert s[1][0] == 7   # quad rank leads

    def test_higher_quad_beats_lower(self):
        hi = [c(14,'s'), c(14,'h'), c(14,'d'), c(14,'c'), c(2,'s')]
        lo = [c(13,'s'), c(13,'h'), c(13,'d'), c(13,'c'), c(14,'h')]
        assert score(hi) > score(lo)

    def test_same_quad_kicker_breaks_tie(self):
        hi = [c(8,'s'), c(8,'h'), c(8,'d'), c(8,'c'), c(14,'s')]
        lo = [c(8,'s'), c(8,'h'), c(8,'d'), c(8,'c'), c(2,'s')]
        assert score(hi) > score(lo)

    def test_7card_finds_quads(self):
        cards = [c(9,'s'), c(9,'h'), c(9,'d'), c(9,'c'), c(2,'h'), c(4,'d'), c(14,'s')]
        assert name(cards) == 'Four of a Kind'


# ── full house ────────────────────────────────────────────────────────────────

class TestFullHouse:
    def test_basic(self):
        cards = [c(14,'s'), c(14,'h'), c(14,'d'), c(13,'s'), c(13,'h')]
        assert name(cards) == 'Full House'
        assert score(cards)[0] == 7

    def test_trips_rank_first(self):
        s = score([c(10,'s'), c(10,'h'), c(10,'d'), c(2,'s'), c(2,'h')])
        assert s[1][0] == 10

    def test_higher_trips_wins(self):
        hi = [c(14,'s'), c(14,'h'), c(14,'d'), c(2,'s'), c(2,'h')]
        lo = [c(13,'s'), c(13,'h'), c(13,'d'), c(14,'s'), c(14,'h')]
        assert score(hi) > score(lo)

    def test_pair_rank_breaks_tie_on_same_trips(self):
        hi = [c(8,'s'), c(8,'h'), c(8,'d'), c(7,'s'), c(7,'h')]
        lo = [c(8,'s'), c(8,'h'), c(8,'d'), c(2,'s'), c(2,'h')]
        assert score(hi) > score(lo)

    def test_7card_picks_best_full_house(self):
        # With AAAKK and 2 extra cards that form lower full house
        cards = [c(14,'s'), c(14,'h'), c(14,'d'), c(13,'s'), c(13,'h'),
                 c(2,'c'), c(2,'d')]
        assert name(cards) == 'Full House'
        s = score(cards)
        assert s[1][0] == 14  # aces-full, not twos-full


# ── flush ─────────────────────────────────────────────────────────────────────

class TestFlush:
    def test_basic(self):
        cards = [c(14,'h'), c(11,'h'), c(9,'h'), c(6,'h'), c(2,'h')]
        assert name(cards) == 'Flush'
        assert score(cards)[0] == 6

    def test_ace_high_flush(self):
        cards = [c(14,'d'), c(13,'d'), c(12,'d'), c(11,'d'), c(9,'d')]
        assert name(cards) == 'Flush'

    def test_higher_flush_wins(self):
        hi = [c(14,'c'), c(10,'c'), c(8,'c'), c(6,'c'), c(4,'c')]
        lo = [c(13,'c'), c(10,'c'), c(8,'c'), c(6,'c'), c(4,'c')]
        assert score(hi) > score(lo)

    def test_flush_kicker_comparison(self):
        hi = [c(10,'s'), c(9,'s'), c(8,'s'), c(7,'s'), c(6,'s')]
        lo = [c(10,'s'), c(9,'s'), c(8,'s'), c(7,'s'), c(2,'s')]
        assert score(hi) > score(lo)

    def test_7card_selects_highest_5_suited(self):
        # 6 spades — should pick the 5 highest
        cards = [c(14,'s'), c(13,'s'), c(12,'s'), c(11,'s'), c(9,'s'),
                 c(2,'s'), c(5,'h')]
        assert name(cards) == 'Flush'
        s = score(cards)
        # Best 5: A K Q J 9
        assert s[1] == (14, 13, 12, 11, 9)


# ── straight ──────────────────────────────────────────────────────────────────

class TestStraight:
    def test_broadway(self):
        # A-K-Q-J-T off-suit = Broadway straight
        cards = [c(14,'s'), c(13,'h'), c(12,'d'), c(11,'c'), c(10,'s')]
        assert name(cards) == 'Straight'
        assert score(cards)[0] == 5

    def test_wheel_ace_low(self):
        # A-2-3-4-5 = wheel, 5-high straight
        cards = [c(14,'s'), c(5,'h'), c(4,'d'), c(3,'c'), c(2,'s')]
        assert name(cards) == 'Straight'
        assert score(cards)[1][0] == 5   # effective high = 5

    def test_wheel_not_ace_high(self):
        wheel = [c(14,'s'), c(5,'h'), c(4,'d'), c(3,'c'), c(2,'s')]
        broadway = [c(14,'s'), c(13,'h'), c(12,'d'), c(11,'c'), c(10,'s')]
        assert score(broadway) > score(wheel)

    def test_six_high_beats_five_high(self):
        hi = [c(6,'s'), c(5,'h'), c(4,'d'), c(3,'c'), c(2,'s')]
        lo = [c(5,'s'), c(4,'h'), c(3,'d'), c(2,'c'), c(14,'s')]
        assert score(hi) > score(lo)

    def test_pair_inside_breaks_straight(self):
        # A-A-2-3-4 has pair → not a straight
        cards = [c(14,'s'), c(14,'h'), c(3,'d'), c(2,'c'), c(4,'s')]
        assert name(cards) != 'Straight'

    def test_7card_finds_best_straight(self):
        # Has 5-high and 6-high straights available
        cards = [c(6,'s'), c(5,'h'), c(4,'d'), c(3,'c'), c(2,'s'),
                 c(14,'h'), c(9,'d')]
        assert name(cards) == 'Straight'
        s = score(cards)
        assert s[1][0] == 6  # picks 6-high, not 5-high


# ── three of a kind ───────────────────────────────────────────────────────────

class TestThreeOfAKind:
    def test_basic(self):
        cards = [c(7,'s'), c(7,'h'), c(7,'d'), c(14,'c'), c(13,'s')]
        assert name(cards) == 'Three of a Kind'
        assert score(cards)[0] == 4

    def test_higher_trips_wins(self):
        hi = [c(14,'s'), c(14,'h'), c(14,'d'), c(2,'c'), c(3,'s')]
        lo = [c(13,'s'), c(13,'h'), c(13,'d'), c(14,'c'), c(12,'s')]
        assert score(hi) > score(lo)


# ── two pair ──────────────────────────────────────────────────────────────────

class TestTwoPair:
    def test_basic(self):
        cards = [c(14,'s'), c(14,'h'), c(13,'d'), c(13,'c'), c(2,'s')]
        assert name(cards) == 'Two Pair'
        assert score(cards)[0] == 3

    def test_higher_top_pair_wins(self):
        hi = [c(14,'s'), c(14,'h'), c(2,'d'), c(2,'c'), c(3,'s')]
        lo = [c(13,'s'), c(13,'h'), c(12,'d'), c(12,'c'), c(14,'s')]
        assert score(hi) > score(lo)

    def test_same_top_pair_second_pair_breaks_tie(self):
        hi = [c(14,'s'), c(14,'h'), c(13,'d'), c(13,'c'), c(2,'s')]
        lo = [c(14,'s'), c(14,'h'), c(12,'d'), c(12,'c'), c(2,'s')]
        assert score(hi) > score(lo)

    def test_same_pairs_kicker_breaks_tie(self):
        hi = [c(8,'s'), c(8,'h'), c(3,'d'), c(3,'c'), c(14,'s')]
        lo = [c(8,'s'), c(8,'h'), c(3,'d'), c(3,'c'), c(2,'s')]
        assert score(hi) > score(lo)

    def test_7card_picks_best_two_pair(self):
        # Hole: A A; Community: K K Q 9 2 → best = A A K K Q
        cards = [c(14,'s'), c(14,'h'), c(13,'d'), c(13,'c'), c(12,'s'),
                 c(9,'d'), c(2,'h')]
        assert name(cards) == 'Two Pair'
        s = score(cards)
        assert s[1][:2] == (14, 13)   # aces and kings


# ── one pair ──────────────────────────────────────────────────────────────────

class TestOnePair:
    def test_basic(self):
        cards = [c(14,'s'), c(14,'h'), c(13,'d'), c(12,'c'), c(11,'s')]
        assert name(cards) == 'One Pair'
        assert score(cards)[0] == 2

    def test_higher_pair_wins(self):
        hi = [c(14,'s'), c(14,'h'), c(2,'d'), c(3,'c'), c(4,'s')]
        lo = [c(13,'s'), c(13,'h'), c(14,'d'), c(12,'c'), c(11,'s')]
        assert score(hi) > score(lo)

    def test_kicker_breaks_tie(self):
        hi = [c(8,'s'), c(8,'h'), c(14,'d'), c(2,'c'), c(3,'s')]
        lo = [c(8,'s'), c(8,'h'), c(13,'d'), c(2,'c'), c(3,'s')]
        assert score(hi) > score(lo)


# ── high card ─────────────────────────────────────────────────────────────────

class TestHighCard:
    def test_basic(self):
        cards = [c(14,'s'), c(13,'h'), c(11,'d'), c(9,'c'), c(7,'s')]
        assert name(cards) == 'High Card'
        assert score(cards)[0] == 1

    def test_ace_high_beats_king_high(self):
        hi = [c(14,'s'), c(10,'h'), c(8,'d'), c(6,'c'), c(4,'s')]
        lo = [c(13,'s'), c(12,'h'), c(11,'d'), c(10,'c'), c(8,'s')]
        assert score(hi) > score(lo)

    def test_second_kicker_breaks_tie(self):
        hi = [c(14,'s'), c(13,'h'), c(8,'d'), c(6,'c'), c(4,'s')]
        lo = [c(14,'s'), c(12,'h'), c(11,'d'), c(9,'c'), c(7,'s')]
        assert score(hi) > score(lo)


# ── hand ranking order ────────────────────────────────────────────────────────

class TestRankingOrder:
    """Confirm every tier beats every lower tier (no rank swaps)."""

    def setup_method(self):
        self.royal    = [c(14,'s'), c(13,'s'), c(12,'s'), c(11,'s'), c(10,'s')]
        self.sf       = [c(9,'h'),  c(8,'h'),  c(7,'h'),  c(6,'h'),  c(5,'h')]
        self.quads    = [c(14,'s'), c(14,'h'), c(14,'d'), c(14,'c'), c(2,'s')]
        self.fh       = [c(14,'s'), c(14,'h'), c(14,'d'), c(13,'s'), c(13,'h')]
        self.flush    = [c(14,'d'), c(11,'d'), c(9,'d'),  c(6,'d'),  c(2,'d')]
        self.straight = [c(10,'s'), c(9,'h'),  c(8,'d'),  c(7,'c'),  c(6,'s')]
        self.trips    = [c(9,'s'),  c(9,'h'),  c(9,'d'),  c(14,'c'), c(13,'s')]
        self.two_pair = [c(14,'s'), c(14,'h'), c(13,'d'), c(13,'c'), c(2,'s')]
        self.one_pair = [c(14,'s'), c(14,'h'), c(13,'d'), c(12,'c'), c(11,'s')]
        self.high     = [c(14,'s'), c(13,'h'), c(11,'d'), c(9,'c'),  c(7,'s')]

    def test_full_hierarchy(self):
        hands = [
            self.royal, self.sf, self.quads, self.fh,
            self.flush, self.straight, self.trips,
            self.two_pair, self.one_pair, self.high,
        ]
        scores = [score(h) for h in hands]
        for i in range(len(scores) - 1):
            assert scores[i] > scores[i + 1], \
                f"Hand at index {i} should beat hand at index {i+1}"


# ── 7-card best-hand selection ────────────────────────────────────────────────

class TestSevenCardBestHand:
    def test_ignores_weaker_cards(self):
        # Royal flush buried in 7 cards with 2 junk cards
        cards = [c(14,'c'), c(13,'c'), c(12,'c'), c(11,'c'), c(10,'c'),
                 c(2,'h'), c(7,'d')]
        assert name(cards) == 'Royal Flush'

    def test_flush_over_pair(self):
        # Has a pair AND a flush — should pick flush
        cards = [c(14,'s'), c(14,'h'),   # pair of aces
                 c(9,'d'), c(8,'d'), c(7,'d'), c(6,'d'), c(2,'d')]   # flush
        assert name(cards) == 'Flush'

    def test_straight_over_two_pair(self):
        cards = [c(10,'s'), c(9,'h'), c(8,'d'), c(7,'c'), c(6,'s'),
                 c(14,'h'), c(14,'d')]   # pair of aces, but straight exists
        assert name(cards) == 'Straight'

    def test_full_house_over_flush(self):
        # Has both full house and flush — should pick full house
        cards = [c(8,'s'), c(8,'h'), c(8,'d'),   # trips
                 c(2,'s'), c(2,'h'),               # pair → full house
                 c(14,'s'), c(9,'s')]               # extra spades
        assert name(cards) == 'Full House'
