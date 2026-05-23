from collections import deque
from .card import Deck
from .hand_evaluator import HandEvaluator

class TexasHoldem:
    def __init__(self, players, small_blind: int = 10, big_blind: int = 20):
        self.players = players
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.dealer_idx = 0
        self.deck = Deck()
        self.community_cards = []
        self.pot = 0

    # ── Public entry point ────────────────────────────────────────────────────

    def play(self):
        print("\n" + "=" * 45)
        print("        Texas Hold'em")
        print("=" * 45)
        print(f"Players : {', '.join(p.name for p in self.players)}")
        print(f"Blinds  : {self.small_blind} / {self.big_blind}")
        print(f"Chips   : {self.players[0].chips} each")
        print("=" * 45)

        hand_num = 0
        while True:
            active = [p for p in self.players if p.chips > 0]
            if len(active) < 2:
                winner = active[0] if active else None
                if winner:
                    print(f"\n{winner.name} wins the game with {winner.chips} chips!")
                break

            hand_num += 1
            print(f"\n{'═' * 45}")
            print(f"  Hand #{hand_num}")

            chips_before = {p: p.chips for p in self.players}
            self.play_hand()

            # Announce any players newly eliminated this hand
            for p in self.players:
                if chips_before[p] > 0 and p.chips == 0:
                    print(f"\n  *** {p.name} has been eliminated! ***")

            if any(p.is_human() and p.chips > 0 for p in self.players):
                try:
                    again = input("\nPlay another hand? (y/n): ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    break
                if again != 'y':
                    break

        print("\n── Final chip counts ──────────────────")
        for p in self.players:
            print(f"  {p.name:<12} {p.chips}")

    # ── Hand lifecycle ────────────────────────────────────────────────────────

    def play_hand(self):
        self.deck.reset()
        self.community_cards = []
        self.pot = 0

        active = [p for p in self.players if p.chips > 0]
        for p in active:
            p.reset_hand()

        n = len(active)
        dealer_pos = self.dealer_idx % n

        # Position assignments (heads-up: dealer = SB)
        if n == 2:
            sb_pos = dealer_pos
            bb_pos = (dealer_pos + 1) % n
            utg_pos = dealer_pos  # SB acts first pre-flop heads-up
        else:
            sb_pos = (dealer_pos + 1) % n
            bb_pos = (dealer_pos + 2) % n
            utg_pos = (dealer_pos + 3) % n

        dealer   = active[dealer_pos]
        sb_player = active[sb_pos]
        bb_player = active[bb_pos]

        print(f"\n  Dealer: {dealer.name}  |  SB: {sb_player.name}  |  BB: {bb_player.name}")

        # Post blinds
        self._place_bet(sb_player, self.small_blind)
        self._place_bet(bb_player, self.big_blind)
        print(f"  Blinds posted. Pot: {self.pot}")

        # Deal hole cards
        for p in active:
            p.hole_cards = self.deck.deal(2)

        # Show human player their hole cards
        for p in active:
            if p.is_human():
                print(f"\n  Your hole cards: {' '.join(str(c) for c in p.hole_cards)}")

        # ── Pre-flop ──────────────────────────────────────────────────────────
        print("\n  ── Pre-flop ──")
        preflop_order = [active[(utg_pos + i) % n] for i in range(n)]
        if not self._betting_round(preflop_order, current_bet=self.big_blind):
            self._end_hand(active)
            return

        # ── Flop ─────────────────────────────────────────────────────────────
        self._reset_street(active)
        self.community_cards += self.deck.deal(3)
        print(f"\n  ── Flop: {self._board_str()} ──")
        postflop = self._postflop_order(active, dealer_pos)
        if not self._betting_round(postflop):
            self._end_hand(active)
            return

        # ── Turn ─────────────────────────────────────────────────────────────
        self._reset_street(active)
        self.community_cards += self.deck.deal(1)
        print(f"\n  ── Turn: {self._board_str()} ──")
        postflop = self._postflop_order(active, dealer_pos)
        if not self._betting_round(postflop):
            self._end_hand(active)
            return

        # ── River ─────────────────────────────────────────────────────────────
        self._reset_street(active)
        self.community_cards += self.deck.deal(1)
        print(f"\n  ── River: {self._board_str()} ──")
        postflop = self._postflop_order(active, dealer_pos)
        self._betting_round(postflop)

        self._end_hand(active)

    # ── Betting round ─────────────────────────────────────────────────────────

    def _betting_round(self, players, current_bet: int = 0) -> bool:
        """
        Run one betting street. Returns True if 2+ players remain in the hand.
        current_bet: the amount everyone must reach (pre-flop = big blind).
        """
        active = [p for p in players if not p.folded]
        if len(active) <= 1:
            return False

        min_raise = self.big_blind
        to_act = deque(p for p in players if not p.folded and not p.all_in)

        while to_act:
            player = to_act.popleft()

            if player.folded or player.all_in:
                continue

            # Stop early if only one non-folded player remains
            if len([p for p in players if not p.folded]) <= 1:
                break

            to_call = current_bet - player.street_bet
            action, amount = player.get_action(
                current_bet=current_bet,
                to_call=to_call,
                min_raise=min_raise,
                pot=self.pot,
                community_cards=self.community_cards,
            )

            if action == 'fold':
                player.folded = True
                print(f"  {player.name} folds.")

            elif action == 'check':
                print(f"  {player.name} checks.")

            elif action == 'call':
                actual = self._place_bet(player, to_call)
                suffix = " (all-in)" if player.all_in else ""
                print(f"  {player.name} calls {actual}{suffix}.  Pot: {self.pot}")

            elif action == 'raise':
                # amount = raise SIZE on top of the call
                actual = self._place_bet(player, to_call + amount)
                new_bet = player.street_bet
                if new_bet > current_bet:
                    raise_size = new_bet - current_bet
                    min_raise = max(min_raise, raise_size)
                    current_bet = new_bet
                    to_act = deque(
                        p for p in players if not p.folded and not p.all_in and p is not player
                    )
                    print(f"  {player.name} raises to {current_bet}.  Pot: {self.pot}")
                else:
                    print(f"  {player.name} goes all-in for {actual}.  Pot: {self.pot}")

            elif action == 'all-in':
                actual = self._place_bet(player, player.chips)
                new_bet = player.street_bet
                if new_bet > current_bet:
                    raise_size = new_bet - current_bet
                    current_bet = new_bet
                    if raise_size >= min_raise:
                        min_raise = raise_size
                    to_act = deque(
                        p for p in players if not p.folded and not p.all_in and p is not player
                    )
                print(f"  {player.name} goes all-in for {new_bet}!  Pot: {self.pot}")

        return len([p for p in players if not p.folded]) > 1

    # ── Showdown / pot award ──────────────────────────────────────────────────

    def _end_hand(self, players):
        active = [p for p in players if not p.folded]

        if len(active) == 1:
            active[0].chips += self.pot
            print(f"\n  {active[0].name} wins the pot of {self.pot}! "
                  f"(Chips: {active[0].chips})")
        else:
            self._showdown(active)

        # Rotate dealer to next player who still has chips
        all_with_chips = [p for p in self.players if p.chips > 0]
        if all_with_chips:
            self.dealer_idx = (self.dealer_idx + 1) % len(all_with_chips)

    def _showdown(self, players):
        print(f"\n  ── Showdown (Board: {self._board_str()}) ──")

        results = []
        for p in players:
            score, hand_name = HandEvaluator.best_hand(p.hole_cards + self.community_cards)
            cards_str = ' '.join(str(c) for c in p.hole_cards)
            print(f"  {p.name:<12} {cards_str}  →  {hand_name}")
            results.append((score, p))

        best_score = max(r[0] for r in results)
        winners = [p for score, p in results if score == best_score]

        share = self.pot // len(winners)
        remainder = self.pot % len(winners)

        for w in winners:
            w.chips += share
        winners[0].chips += remainder

        if len(winners) == 1:
            print(f"\n  {winners[0].name} wins the pot of {self.pot}! "
                  f"(Chips: {winners[0].chips})")
        else:
            names = ' & '.join(w.name for w in winners)
            print(f"\n  Split pot! {names} each receive {share}.")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _place_bet(self, player, amount: int) -> int:
        amount = min(amount, player.chips)
        player.chips -= amount
        player.street_bet += amount
        self.pot += amount
        if player.chips == 0:
            player.all_in = True
        return amount

    def _reset_street(self, players):
        for p in players:
            p.street_bet = 0

    def _postflop_order(self, players, dealer_pos: int):
        n = len(players)
        return [
            players[(dealer_pos + i) % n]
            for i in range(1, n + 1)
            if not players[(dealer_pos + i) % n].folded
        ]

    def _board_str(self) -> str:
        return ' '.join(str(c) for c in self.community_cards)
