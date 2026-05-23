from .hand_evaluator import HandEvaluator


class Player:
    def __init__(self, name: str, chips: int = 1000):
        self.name = name
        self.chips = chips
        self.hole_cards = []
        self.street_bet = 0   # chips put in this betting street
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


class HumanPlayer(Player):
    def is_human(self) -> bool:
        return True

    def get_action(self, current_bet, to_call, min_raise, pot, community_cards):
        print(f"\n  ── Your Turn ─────────────────────────")
        print(f"  Chips: {self.chips}  |  Pot: {pot}")
        if community_cards:
            print(f"  Board : {' '.join(str(c) for c in community_cards)}")
        print(f"  Hand  : {' '.join(str(c) for c in self.hole_cards)}")

        can_check = to_call == 0
        if can_check:
            print(f"  Actions: check (c)  |  bet/raise <amount> (r <n>)  |  fold (f)")
        else:
            remaining_after_call = self.chips - to_call
            print(f"  To call: {min(to_call, self.chips)}")
            print(f"  Actions: call (c)  |  raise <amount> (r <n>)  |  all-in (a)  |  fold (f)")

        while True:
            try:
                raw = input("  > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return ('fold', 0)

            if not raw:
                continue

            parts = raw.split()
            cmd = parts[0]

            if cmd in ('f', 'fold'):
                return ('fold', 0)

            if cmd in ('c', 'call', 'check'):
                if can_check:
                    return ('check', 0)
                return ('call', to_call)

            if cmd in ('a', 'allin', 'all-in', 'all_in'):
                return ('all-in', self.chips)

            if cmd in ('r', 'raise', 'bet'):
                if len(parts) < 2:
                    print(f"  Specify amount. Min raise size: {min_raise}")
                    continue
                try:
                    amount = int(parts[1])
                except ValueError:
                    print("  Invalid amount.")
                    continue
                total_needed = to_call + amount
                if amount < min_raise and total_needed < self.chips:
                    print(f"  Minimum raise size is {min_raise}.")
                    continue
                return ('raise', amount)

            print("  Unknown command. Try: c (check/call), r <n> (raise), a (all-in), f (fold)")


class BotPlayer(Player):
    def __init__(self, name: str, chips: int = 1000, aggression: float = 0.5):
        super().__init__(name, chips)
        self.aggression = aggression  # 0.0 (tight/passive) to 1.0 (loose/aggressive)

    def get_action(self, current_bet, to_call, min_raise, pot, community_cards):
        strength = self._hand_strength(community_cards)

        # Simple pot-odds check
        pot_odds = to_call / (pot + to_call) if to_call > 0 and pot > 0 else 0.0

        raise_thresh = 0.65 - self.aggression * 0.15
        call_thresh  = 0.35 - self.aggression * 0.10
        fold_thresh  = 0.20 - self.aggression * 0.08

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

        # Small bonus for high kickers within the same hand tier
        kicker_bonus = (score[1][0] / 14.0) * 0.04 if score[1] else 0.0
        return min(1.0, base + kicker_bonus)

    def _preflop_strength(self) -> float:
        if len(self.hole_cards) < 2:
            return 0.3

        r1, r2 = self.hole_cards[0].rank, self.hole_cards[1].rank
        high, low = max(r1, r2), min(r1, r2)
        suited = self.hole_cards[0].suit == self.hole_cards[1].suit

        if r1 == r2:
            return 0.50 + (r1 - 2) / 12.0 * 0.45  # 22→0.50, AA→0.95

        high_s = (high - 2) / 12.0
        low_s  = (low  - 2) / 12.0
        gap    = high - low

        base = high_s * 0.55 + low_s * 0.25
        if suited:  base += 0.05
        if gap == 1: base += 0.04
        elif gap == 2: base += 0.02

        return min(0.72, base)
