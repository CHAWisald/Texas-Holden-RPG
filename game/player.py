import random

from .hand_evaluator import HandEvaluator


class Player:
    def __init__(self, name: str, chips: int = 1000):
        self.name = name
        self.chips = chips
        self.hole_cards = []
        self.street_bet = 0
        self.folded = False
        self.all_in = False

    def reset_hand(self):
        self.hole_cards = []
        self.street_bet = 0
        self.folded = False
        self.all_in = False

    def is_human(self) -> bool:
        return False

    def get_action(self, current_bet, to_call, min_raise, pot, community_cards):
        raise NotImplementedError

    def decide_to_cheat(self, deck) -> tuple:
        """Return (will_cheat: bool, chosen_hand: str|None)."""
        return False, None

    def decide_to_accuse(self, elapsed: float, big_blind: int) -> bool:
        return False


class HumanPlayer(Player):
    def is_human(self) -> bool:
        return True

    def get_action(self, current_bet, to_call, min_raise, pot, community_cards):
        from .cheat_system import timed_input

        print(f"\n  ── Your Turn ─────────────────────────")
        print(f"  Chips: {self.chips}  |  Pot: {pot}")
        if community_cards:
            print(f"  Board : {' '.join(str(c) for c in community_cards)}")
        print(f"  Hand  : {' '.join(str(c) for c in self.hole_cards)}")

        can_check = to_call == 0
        auto = 'c' if can_check else 'f'

        if can_check:
            print(f"  Actions: check (c)  |  raise <n> (r <n>)  |  fold (f)  [30s]")
        else:
            print(f"  To call: {min(to_call, self.chips)}")
            print(f"  Actions: call (c)  |  raise <n> (r <n>)  |  all-in (a)  |  fold (f)  [30s]")

        raw = timed_input("  > ", timeout=30.0, default=auto)
        if not raw:
            raw = auto

        parts = raw.strip().lower().split()
        cmd   = parts[0] if parts else auto

        if cmd in ('f', 'fold'):
            return ('fold', 0)

        if cmd in ('c', 'call', 'check'):
            return ('check', 0) if can_check else ('call', to_call)

        if cmd in ('a', 'allin', 'all-in', 'all_in'):
            return ('all-in', self.chips)

        if cmd in ('r', 'raise', 'bet'):
            if len(parts) >= 2:
                try:
                    amount = int(parts[1])
                    if amount < min_raise and to_call + amount < self.chips:
                        print(f"  Min raise is {min_raise}, using that.")
                        amount = min_raise
                    return ('raise', amount)
                except ValueError:
                    pass
            print(f"  No valid amount — raising minimum ({min_raise}).")
            return ('raise', min_raise)

        print(f"  Unrecognised — defaulting to {'check' if can_check else 'fold'}.")
        return ('check', 0) if can_check else ('fold', 0)

    def decide_to_cheat(self, deck) -> tuple:
        from .cheat_system import timed_input, CHEAT_HAND_OPTIONS, CHEAT_HAND_LABELS

        print("\n  You are the Dealer! (secret decision — others only see shuffle time)")
        raw = timed_input(
            "  [H]onest shuffle or [C]heat? [30s]: ",
            timeout=30.0, default='h'
        )

        if raw.lower().startswith('c'):
            print("  Pick your hand:")
            for i, h in enumerate(CHEAT_HAND_OPTIONS, 1):
                print(f"    {i}. {h}  ({CHEAT_HAND_LABELS[h]})")
            pick = timed_input("  Choice [1-5, 10s]: ", timeout=10.0, default='1')
            try:
                idx = max(0, min(int(pick) - 1, len(CHEAT_HAND_OPTIONS) - 1))
            except ValueError:
                idx = 0
            chosen = CHEAT_HAND_OPTIONS[idx]
            print(f"  Dealing yourself: {chosen}  ({CHEAT_HAND_LABELS[chosen]})")
            return True, chosen

        return False, None

    def decide_to_accuse(self, elapsed: float, big_blind: int) -> bool:
        from .cheat_system import timed_input

        ans = timed_input(
            f"  Accuse the dealer? (costs {2 * big_blind} chips) [y/n, 15s]: ",
            timeout=15.0, default='n'
        )
        return ans.lower().startswith('y')


class BotPlayer(Player):
    def __init__(self, name: str, chips: int = 1000, aggression: float = 0.5):
        super().__init__(name, chips)
        self.aggression = aggression

    def get_action(self, current_bet, to_call, min_raise, pot, community_cards):
        strength = self._hand_strength(community_cards)

        pot_odds = to_call / (pot + to_call) if to_call > 0 and pot > 0 else 0.0

        raise_thresh = 0.65 - self.aggression * 0.15
        call_thresh  = 0.35 - self.aggression * 0.10

        if strength >= raise_thresh and self.chips > to_call + min_raise:
            raise_size = max(min_raise, int(pot * 0.6 * strength))
            raise_size = min(raise_size, self.chips - to_call)
            if raise_size >= min_raise:
                return ('raise', raise_size)

        if strength >= call_thresh or (to_call > 0 and strength > pot_odds * 1.2):
            if to_call == 0:
                return ('check', 0)
            if to_call >= self.chips:
                return ('all-in', self.chips) if strength >= 0.35 else ('fold', 0)
            return ('call', to_call)

        if to_call == 0:
            return ('check', 0)

        return ('fold', 0)

    def decide_to_cheat(self, deck) -> tuple:
        if random.random() < self.aggression * 0.25:
            chosen = random.choice(['AA', 'KK', 'QQ', 'AKs', 'AKo'])
            return True, chosen
        return False, None

    def decide_to_accuse(self, elapsed: float, big_blind: int) -> bool:
        if self.chips < 2 * big_blind:
            return False
        # Honest range 12.5–17.5s, cheat range 15–20s — overlap is 15–17.5s
        if elapsed > 17.5:
            prob = 0.80     # outside honest range entirely
        elif elapsed > 17.0:
            prob = 0.60     # high end of overlap
        elif elapsed > 15.0:
            prob = 0.35     # ambiguous overlap zone
        elif elapsed > 14.0:
            prob = 0.12     # near the boundary, probably honest
        else:
            prob = 0.03     # clearly honest territory
        return random.random() < prob

    def _hand_strength(self, community_cards) -> float:
        all_cards = self.hole_cards + community_cards

        if not community_cards:
            return self._preflop_strength()

        if len(all_cards) < 5:
            return (self._preflop_strength() + 0.3) / 2.0

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

    def _preflop_strength(self) -> float:
        if len(self.hole_cards) < 2:
            return 0.3

        r1, r2 = self.hole_cards[0].rank, self.hole_cards[1].rank
        high, low = max(r1, r2), min(r1, r2)
        suited = self.hole_cards[0].suit == self.hole_cards[1].suit

        if r1 == r2:
            return 0.50 + (r1 - 2) / 12.0 * 0.45

        base = (high - 2) / 12.0 * 0.55 + (low - 2) / 12.0 * 0.25
        gap = high - low
        if suited:   base += 0.05
        if gap == 1: base += 0.04
        elif gap == 2: base += 0.02

        return min(0.72, base)
