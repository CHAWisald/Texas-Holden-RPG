import random
from collections import deque
from .card import Deck
from .cheat_system import CheatSystem
from .hand_evaluator import HandEvaluator
from .roles import RoleSystem, RoleType

class TexasHoldem:
    def __init__(self, players, small_blind: int = 10, big_blind: int = 20):
        self.players = players
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.dealer_idx = 0
        self.deck = Deck()
        self.community_cards = []
        self.pot = 0
        self.cheat_system = CheatSystem(big_blind)
        self.role_system  = RoleSystem(big_blind)

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

            # ── Post-hand revival & elimination ───────────────────────────────
            newly_bust = [p for p in self.players
                          if chips_before[p] > 0 and p.chips == 0]
            revived = set()
            for p in newly_bust:
                if self.role_system.handle_bust(p):
                    revived.add(p)

            for p in newly_bust:
                if p not in revived:
                    print(f"\n  *** {p.name} has been eliminated! ***")

            # Devil-debt countdown (happens after the hand is fully resolved)
            all_in_play = [p for p in self.players if p.chips > 0]
            self.role_system.tick_devil_debts(all_in_play)

            # ── Stop if human is out ──────────────────────────────────────────
            human_alive = any(p.is_human() and p.chips > 0 for p in self.players)
            if any(p.is_human() for p in self.players) and not human_alive:
                print("\n  You have been eliminated. Game over.")
                break

            # ── Between-hand role abilities ───────────────────────────────────
            active_now = [p for p in self.players if p.chips > 0]
            for p in active_now:
                self.role_system.offer_curse_ability(p, active_now)
                self.role_system.offer_shoot_ability(p, active_now)

            # Re-check for victims of a shooting
            active_now = [p for p in self.players if p.chips > 0]
            if len(active_now) < 2:
                break
            if any(p.is_human() for p in self.players) and \
               not any(p.is_human() and p.chips > 0 for p in self.players):
                print("\n  You have been eliminated. Game over.")
                break

            # ── Continue prompt (only when human is still in) ─────────────────
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

        print(f"\n  Dealer: {dealer.name}  |  SB: {sb_player.name}  |  BB: {bb_player.name}")
        self._show_roles(active)

        self._place_bet(sb_player, self.small_blind)
        self._place_bet(bb_player, self.big_blind)
        print(f"  Blinds posted. Pot: {self.pot}")

        # ── Shuffle / cheat phase ─────────────────────────────────────────────
        cheated, elapsed, chosen_hand = self.cheat_system.shuffle_phase(dealer, self.deck)
        accusers = self.cheat_system.accusation_phase(active, dealer, elapsed)

        lucky_escape = self.role_system.check_lucky_escape(dealer) if accusers else False
        caught = self.cheat_system.resolve(accusers, dealer, cheated, escape=lucky_escape)

        if caught:
            self.deck.reset()
            for p in active:
                p.hole_cards = self.deck.deal(2)
        else:
            for p in active:
                if cheated and p is dealer:
                    p.hole_cards = self.cheat_system.deal_cheat_hand(chosen_hand, self.deck)
                elif p.role == RoleType.LUCKY:
                    p.hole_cards = self.role_system.lucky_deal(p, self.deck)
                else:
                    p.hole_cards = self.deck.deal(2)

        # ── Apply devil / curse effects on dealt hands ────────────────────────
        for p in active:
            if p.is_devil:
                self.role_system.apply_devil_hand(p, self.deck)
            if p.curse_hands_left > 0:
                self.role_system.apply_victim_curse(p, self.deck)

        # Show human their (possibly modified) hole cards
        for p in active:
            if p.is_human():
                label = "Your new hole cards" if caught else "Your hole cards"
                print(f"\n  {label}: {' '.join(str(c) for c in p.hole_cards)}")
                if p.is_devil:
                    print(f"  [Devil's Ledger] Debt: {p.devil_debt} | "
                          f"Hands left: {p.devil_hands}")

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
        active = [p for p in players if not p.folded]
        if len(active) <= 1:
            return False

        min_raise = self.big_blind
        to_act = deque(p for p in players if not p.folded and not p.all_in)

        while to_act:
            player = to_act.popleft()

            if player.folded or player.all_in:
                continue

            if len([p for p in players if not p.folded]) <= 1:
                break

            # Bot ability: small chance to use role ability before betting
            if not player.is_human():
                self._try_bot_inhand_ability(player, players)
                self._fold_dead_players(players)
                if player.chips == 0:
                    player.folded = True
                if player.folded or player.all_in:
                    continue
                if len([p for p in players if not p.folded]) <= 1:
                    break

            to_call = current_bet - player.street_bet
            action, amount = player.get_action(
                current_bet=current_bet,
                to_call=to_call,
                min_raise=min_raise,
                pot=self.pot,
                community_cards=self.community_cards,
                role_system=self.role_system,
                all_players=players,
            )

            # Fold any players shot dead by a human ability use this action
            self._fold_dead_players(players)

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
                actual = self._place_bet(player, to_call + amount)
                new_bet = player.street_bet
                if new_bet > current_bet:
                    raise_size = new_bet - current_bet
                    min_raise  = max(min_raise, raise_size)
                    current_bet = new_bet
                    to_act = deque(
                        p for p in players if not p.folded and not p.all_in and p is not player
                    )
                    print(f"  {player.name} raises to {current_bet}.  Pot: {self.pot}")
                else:
                    print(f"  {player.name} goes all-in for {actual}.  Pot: {self.pot}")

            elif action == 'all-in':
                actual  = self._place_bet(player, player.chips)
                new_bet = player.street_bet
                if new_bet > current_bet:
                    raise_size  = new_bet - current_bet
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
            self.role_system.detect_bluff_reward(active[0], self.community_cards)
        else:
            self._showdown(active)

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
        winners    = [p for score, p in results if score == best_score]

        share     = self.pot // len(winners)
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
        player.chips     -= amount
        player.street_bet += amount
        self.pot          += amount
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

    def _fold_dead_players(self, players):
        """Fold any player shot dead (chips=0 but not all-in) mid-hand."""
        for p in players:
            if p.chips == 0 and not p.folded and not p.all_in:
                p.folded = True

    def _try_bot_inhand_ability(self, player, players):
        """Give bots a small chance to use their role ability on their turn."""
        if player.role == RoleType.GUNNER and random.random() < 0.05:
            targets = [p for p in players if p is not player and p.chips > 0]
            self.role_system.offer_shoot_ability(player, targets)
        elif player.role == RoleType.CURSED and not player.has_cursed and random.random() < 0.05:
            targets = [p for p in players if p is not player and p.chips > 0]
            self.role_system.offer_curse_ability(player, targets)

    def _show_roles(self, players):
        parts = [f"{p.name}({p.role.value if p.role else 'no role'})"
                 for p in players]
        print(f"  Roles   : {', '.join(parts)}")
