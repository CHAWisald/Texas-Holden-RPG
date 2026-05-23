from itertools import combinations
from collections import Counter


HAND_NAMES = {
    10: 'Royal Flush', 9: 'Straight Flush', 8: 'Four of a Kind',
    7: 'Full House',   6: 'Flush',          5: 'Straight',
    4: 'Three of a Kind', 3: 'Two Pair',    2: 'One Pair', 1: 'High Card',
}


class HandEvaluator:
    @classmethod
    def best_hand(cls, cards):
        """Return (score_tuple, hand_name) for best 5-card hand from 5–7 cards."""
        if len(cards) < 5:
            return None
        best = max(cls._score(combo) for combo in combinations(cards, 5))
        return best, HAND_NAMES[best[0]]

    @classmethod
    def _score(cls, cards):
        ranks = sorted((c.rank for c in cards), reverse=True)
        suits = [c.suit for c in cards]

        is_flush = len(set(suits)) == 1
        is_straight, s_ranks = cls._check_straight(ranks)

        counts = Counter(ranks)
        freq = sorted(counts.items(), key=lambda x: (x[1], x[0]), reverse=True)
        ordered = tuple(r for r, _ in freq)

        if is_straight and is_flush:
            return (10, tuple(s_ranks)) if s_ranks[0] == 14 else (9, tuple(s_ranks))
        if freq[0][1] == 4:
            return (8, ordered)
        if freq[0][1] == 3 and freq[1][1] == 2:
            return (7, ordered)
        if is_flush:
            return (6, tuple(ranks))
        if is_straight:
            return (5, tuple(s_ranks))
        if freq[0][1] == 3:
            return (4, ordered)
        if freq[0][1] == 2 and freq[1][1] == 2:
            return (3, ordered)
        if freq[0][1] == 2:
            return (2, ordered)
        return (1, tuple(ranks))

    @staticmethod
    def _check_straight(ranks):
        """ranks: sorted-descending list of 5 ranks. Returns (is_straight, effective_ranks)."""
        if len(set(ranks)) < 5:
            return False, ranks  # has pairs

        if ranks[0] - ranks[4] == 4:
            return True, ranks

        # Ace-low wheel: A-2-3-4-5
        if ranks[0] == 14 and ranks[1:] == [5, 4, 3, 2]:
            return True, [5, 4, 3, 2, 1]

        return False, ranks
