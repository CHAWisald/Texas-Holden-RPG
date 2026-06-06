import random
from enum import Enum

from .cheat_system import timed_input


class RoleType(Enum):
    CURSED = "The Cursed"
    GUNNER = "The Gunner"
    LUCKY  = "The Lucky"


ROLE_DESCRIPTIONS = {
    RoleType.CURSED: (
        "Bust → sell your soul: receive 20BB chips on loan.\n"
        "    Devil state: each hand your cards may be downgraded or swapped.\n"
        "    Repay the full debt within 5–8 hands or be eliminated.\n"
        "    Once per game: curse one opponent — their hand is tampered for 3–5 hands.\n"
        "    Bluff reward: winning uncontested with a weak hand forgives 5BB of debt."
    ),
    RoleType.GUNNER: (
        "Bust → shoot yourself for 20BB chips (uses one bullet).\n"
        "    Once per game: burn chips to shoot & eliminate another player.\n"
        "    Each shot costs double the last (starts at 10BB). Gun can't be reset."
    ),
    RoleType.LUCKY: (
        "Each hand you draw 3 hole cards and keep the best 2.\n"
        "    30% chance to be immune when cursed or shot.\n"
        "    30% chance the prosecutor lets you go if caught cheating."
    ),
}


class RoleSystem:
    DEVIL_LOAN_BB  = 20
    DEVIL_DEBT_BB  = 25   # loan + interest
    GUNNER_BASE_BB = 10   # base cost to shoot others (doubles per shot)
    LUCKY_IMMUNITY = 0.30
    LUCKY_ESCAPE   = 0.30
    CURSE_MIN      = 3    # hands a cursed victim suffers
    CURSE_MAX      = 5

    def __init__(self, big_blind: int):
        self.bb = big_blind

    # ── Revival on bust ───────────────────────────────────────────────────────

    def handle_bust(self, player) -> bool:
        """Called when a player just hit 0 chips. Returns True if revived."""
        if player.role == RoleType.CURSED:
            return self._cursed_bust(player)
        if player.role == RoleType.GUNNER:
            return self._gunner_bust(player)
        return False

    def _cursed_bust(self, player) -> bool:
        if player.devil_debt > 0:
            # Already defaulted on debt — can't deal again
            return False

        loan   = self.DEVIL_LOAN_BB * self.bb
        total  = self.DEVIL_DEBT_BB * self.bb
        period = random.randint(5, 8)

        if player.is_human():
            print(f"\n  ╔══ The Devil's Offer ════════════════════╗")
            print(f"  ║  Loan : {loan} chips                      ║")
            print(f"  ║  Repay: {total} chips within {period} hands       ║")
            print(f"  ║  Risk : your hand may be tampered each  ║")
            print(f"  ║         round while in devil state.     ║")
            print(f"  ╚════════════════════════════════════════╝")
            ans = timed_input("  Accept the Devil's deal? [y/n, 15s]: ",
                              timeout=15.0, default='n')
            if not ans.lower().startswith('y'):
                return False
        else:
            print(f"\n  *** {player.name} shakes hands with the Devil! "
                  f"({loan} chips, repay {total} in {period} hands) ***")

        player.chips       = loan
        player.devil_debt  = total
        player.devil_hands = period
        player.is_devil    = True
        if player.is_human():
            print(f"  You received {loan} chips. "
                  f"Debt: {total} | Hands remaining: {period}")
        return True

    def _gunner_bust(self, player) -> bool:
        if player.died_by_revolver:
            return False  # already killed themselves via ability this hand

        chips   = self.DEVIL_LOAN_BB * self.bb
        chamber = player.gun_current_chamber + 1

        if player.is_human():
            print(f"\n  ╔══ Russian Roulette ══════════════════════╗")
            print(f"  ║  Chamber {chamber}/6 — pull the trigger!      ║")
            print(f"  ║  CLICK → +{chips} chips and survive.      ║")
            print(f"  ║  BANG  → truly eliminated.              ║")
            print(f"  ╚══════════════════════════════════════════╝")
            ans = timed_input("  Shoot yourself? [y/n, 15s]: ",
                              timeout=15.0, default='n')
            if not ans.lower().startswith('y'):
                return False
        else:
            print(f"\n  *** {player.name} pulls the trigger! Chamber {chamber}/6 ***")

        player.bullets_used += 1
        fired = self._fire_revolver(player)

        if fired:
            if player.is_human():
                print(f"  *** BANG! The gun fires — you are eliminated! ***")
            else:
                print(f"  *** BANG! {player.name} is eliminated by their own gun! ***")
            player.died_by_revolver = True
            return False

        player.chips += chips
        if player.is_human():
            print(f"  *CLICK* You survive! +{chips} chips.")
        else:
            print(f"  *** *CLICK* {player.name} survives! +{chips} chips ***")
        return True

    # ── Devil-state hand tampering ────────────────────────────────────────────

    def apply_devil_hand(self, player, deck):
        """Apply a random negative card effect to a player in devil state."""
        if not player.is_devil:
            return
        if random.random() > 0.70:   # 70% chance of an effect triggering
            return
        if random.random() < 0.50:
            self._downgrade_hand(player, deck)
        else:
            self._swap_card(player, deck)

    def _downgrade_hand(self, player, deck):
        cards = player.hole_cards
        if len(cards) < 2:
            return

        if cards[0].rank == cards[1].rank:
            # Break the pair by replacing one card with junk
            junk = self._draw_junk(deck, avoid_rank=cards[0].rank)
            if not junk:
                return
            old = cards[0]
            player.hole_cards[0] = junk
            deck.cards.append(old)
            deck.cards.remove(junk)
            msg = "[Devil] Your pair was broken — downgraded to High Card."
        else:
            # Replace the higher card with junk
            idx = 0 if cards[0].rank > cards[1].rank else 1
            junk = self._draw_junk(deck, avoid_rank=cards[idx].rank)
            if not junk:
                return
            old = cards[idx]
            player.hole_cards[idx] = junk
            deck.cards.append(old)
            deck.cards.remove(junk)
            msg = "[Devil] Your best card was replaced with trash."

        if player.is_human():
            print(f"\n  {msg}")
            print(f"  New hand: {' '.join(str(c) for c in player.hole_cards)}")
        else:
            print(f"\n  [Devil] {player.name}'s hand was cursed.")

    def _swap_card(self, player, deck):
        idx      = random.randint(0, len(player.hole_cards) - 1)
        old_card = player.hole_cards[idx]
        new_card = self._draw_junk(deck, avoid_rank=old_card.rank)
        if not new_card:
            return
        player.hole_cards[idx] = new_card
        deck.cards.append(old_card)
        deck.cards.remove(new_card)

        if player.is_human():
            print(f"\n  [Devil] One of your cards was swapped!")
            print(f"  {old_card} → {new_card}")
            print(f"  New hand: {' '.join(str(c) for c in player.hole_cards)}")
        else:
            print(f"\n  [Devil] {player.name}'s hand was tampered with.")

    def _draw_junk(self, deck, avoid_rank: int):
        """Pick a low-rank card from the remaining deck."""
        candidates = [c for c in deck.cards if c.rank != avoid_rank and c.rank <= 7]
        if not candidates:
            candidates = [c for c in deck.cards if c.rank != avoid_rank]
        return random.choice(candidates) if candidates else None

    # ── Curse-victim hand tampering ───────────────────────────────────────────

    def apply_victim_curse(self, player, deck):
        """Called each hand for players cursed by a Cursed-role player."""
        if player.curse_hands_left <= 0:
            return
        player.curse_hands_left -= 1
        if random.random() < 0.50:
            self._downgrade_hand(player, deck)
        else:
            self._swap_card(player, deck)
        if player.curse_hands_left == 0:
            if player.is_human():
                print("\n  [Curse lifted] The dark influence fades.")
            else:
                print(f"\n  [Curse lifted] {player.name} is no longer cursed.")

    # ── Devil debt countdown ──────────────────────────────────────────────────

    def tick_devil_debts(self, players):
        """Call after each hand to count down and enforce repayment."""
        for p in players:
            if p.role != RoleType.CURSED or not p.is_devil or p.devil_debt <= 0:
                continue
            p.devil_hands -= 1
            if p.is_human():
                print(f"\n  [Devil's Ledger] Debt: {p.devil_debt} chips | "
                      f"Hands left: {p.devil_hands}")
            if p.devil_hands <= 0:
                if p.chips >= p.devil_debt:
                    paid = p.devil_debt
                    p.chips    -= paid
                    p.devil_debt = 0
                    p.is_devil   = False
                    print(f"\n  *** {p.name} repaid the Devil! "
                          f"({paid} chips paid. Remaining: {p.chips}) ***")
                else:
                    print(f"\n  *** {p.name} defaulted on the Devil's loan! "
                          f"Soul forfeit — eliminated. ***")
                    p.chips    = 0
                    p.devil_debt = 0
                    p.is_devil   = False

    # ── Bluff reward (Cursed) ─────────────────────────────────────────────────

    def detect_bluff_reward(self, winner, community_cards):
        """
        When the Cursed player wins uncontested (everyone folded), check if
        they held a weak hand and reward them with 5BB debt forgiveness.
        Only surfaces feedback to the human player.
        """
        if winner.role != RoleType.CURSED or not winner.is_devil or winner.devil_debt <= 0:
            return
        if not winner.is_human():
            return

        from .hand_evaluator import HandEvaluator
        all_cards = winner.hole_cards + community_cards
        if len(all_cards) < 5:
            return

        _, hand_name = HandEvaluator.best_hand(all_cards)
        if hand_name in ('High Card', 'One Pair'):
            forgiven         = 5 * self.bb
            winner.devil_debt = max(0, winner.devil_debt - forgiven)
            print(f"\n  [Devil's Ledger] Bluff detected — 5BB ({forgiven}) forgiven.")
            print(f"  Remaining debt: {winner.devil_debt} chips.")
            if winner.devil_debt == 0:
                winner.is_devil = False
                print("  Debt cleared! You are free from the Devil.")

    # ── Cursed: curse an opponent ─────────────────────────────────────────────

    def offer_curse_ability(self, cursed_player, all_players):
        """Offer the Cursed player their one-time ability to curse an opponent."""
        if cursed_player.role != RoleType.CURSED or cursed_player.has_cursed:
            return

        targets = [p for p in all_players
                   if p is not cursed_player and p.chips > 0]
        if not targets:
            return

        if cursed_player.is_human():
            self._human_curse(cursed_player, targets)
        else:
            self._bot_curse(cursed_player, targets)

    def _human_curse(self, player, targets):
        print(f"\n  ╔══ Devil's Gift (one-time) ═════════════╗")
        print(f"  ║  Curse an opponent for {self.CURSE_MIN}–{self.CURSE_MAX} hands.   ║")
        print(f"  ║  Their hole cards will be tampered.   ║")
        print(f"  ║  This ability expires if unused.      ║")
        print(f"  ╚════════════════════════════════════════╝")
        print("  Targets:")
        for i, p in enumerate(targets, 1):
            print(f"    {i}. {p.name}  ({p.chips} chips)")
        print(f"    0. Skip")
        raw = timed_input(f"  Who to curse? [0–{len(targets)}, 15s]: ",
                          timeout=15.0, default='0')
        try:
            idx = int(raw.strip())
        except ValueError:
            idx = 0
        if 1 <= idx <= len(targets):
            self._do_curse(player, targets[idx - 1])

    def _bot_curse(self, player, targets):
        if random.random() > 0.25:  # bots curse ~25% chance each hand
            return
        target = max(targets, key=lambda p: p.chips)
        self._do_curse(player, target)

    def _do_curse(self, cursed_by, target):
        duration = random.randint(self.CURSE_MIN, self.CURSE_MAX)
        cursed_by.has_cursed = True
        if self._lucky_immune(target, "the curse"):
            return
        target.curse_hands_left = duration
        print(f"\n  *** {cursed_by.name} curses {target.name} "
              f"for {duration} hands! ***")
        if target.is_human():
            print(f"  Your hole cards will be tampered for {duration} hands.")

    # ── Gunner: shoot an opponent ─────────────────────────────────────────────

    def offer_shoot_ability(self, gunner, all_players):
        """Offer the Gunner player the ability to shoot an opponent or themselves."""
        if gunner.role != RoleType.GUNNER:
            return

        cost = self.GUNNER_BASE_BB * self.bb * (2 ** gunner.bullets_used)
        targets = [p for p in all_players if p is not gunner and p.chips > 0]

        # Humans always see the menu (self-shoot is free; opponent cost shown if affordable)
        if gunner.is_human():
            self._human_shoot(gunner, targets, cost)
        else:
            # Bots only act if they can shoot an opponent or feel desperate
            if gunner.chips >= cost and targets:
                self._bot_shoot(gunner, targets, cost)
            elif gunner.chips < cost * 0.5:
                # Very low chips — small chance to self-shoot for chips
                import random
                if random.random() < 0.05:
                    self._do_shoot_self(gunner, self.DEVIL_LOAN_BB * self.bb)

    def _human_shoot(self, player, targets, cost):
        revival   = self.DEVIL_LOAN_BB * self.bb
        next_cost = cost * 2
        chamber   = player.gun_current_chamber + 1
        can_afford = player.chips >= cost
        print(f"\n  ╔══ Gunner's Revolver ════════════════════╗")
        print(f"  ║  Chamber {chamber}/6 — Russian roulette.      ║")
        if can_afford and targets:
            print(f"  ║  Shoot opponent — {cost} chips, may miss.  ║")
        elif targets:
            print(f"  ║  Shoot opponent — {cost} chips (can't afford). ║")
        else:
            print(f"  ║  No targets available.                  ║")
        print(f"  ║  Shoot yourself — gain {revival} (or die).  ║")
        print(f"  ║  Next opponent-shot cost: {next_cost} chips.  ║")
        print(f"  ╚═════════════════════════════════════════╝")
        if can_afford and targets:
            print("  Targets:")
            for i, p in enumerate(targets, 1):
                print(f"    {i}. {p.name}  ({p.chips} chips)")
        print(f"    0. Shoot yourself (+{revival} on click / eliminated on bang)")
        print(f"   -1. Holster gun")
        max_idx = len(targets) if can_afford else 0
        raw = timed_input(f"  Who to shoot? [-1..{max_idx}, 15s]: ",
                          timeout=15.0, default='-1')
        try:
            idx = int(raw.strip())
        except ValueError:
            idx = -1
        if idx == 0:
            self._do_shoot_self(player, revival)
        elif can_afford and 1 <= idx <= len(targets):
            self._do_shoot(player, targets[idx - 1], cost)

    def _bot_shoot(self, player, targets, cost):
        roll = random.random()
        if roll < 0.05 and player.chips < cost:
            # Low on chips — gamble with self-shot
            revival = self.DEVIL_LOAN_BB * self.bb
            self._do_shoot_self(player, revival)
        elif roll < 0.15 and targets:
            target = max(targets, key=lambda p: p.chips)
            self._do_shoot(player, target, cost)

    def _do_shoot(self, shooter, target, cost):
        shooter.chips        -= cost
        shooter.bullets_used += 1

        immune = self._lucky_immune(target, "the bullet")
        fired  = self._fire_revolver(shooter)

        if immune:
            print(f"\n  *** {shooter.name} fired at {target.name}! "
                  f"({cost} chips burned — {'BANG' if fired else 'click'}, but immune!) ***")
            return

        if not fired:
            print(f"\n  *** *CLICK* — {shooter.name} pulls the trigger on "
                  f"{target.name}... misfires! ({cost} chips burned) ***")
            return

        target.chips = 0
        self._reload_revolver(shooter)
        print(f"\n  *** BANG! {shooter.name} shoots {target.name}! "
              f"({cost} chips burned — {target.name} eliminated! Gun reloaded.) ***")

    def _do_shoot_self(self, player, revival_chips):
        """Player voluntarily shoots themselves mid-game. Revolver applies."""
        player.bullets_used += 1
        fired = self._fire_revolver(player)

        if fired:
            player.chips = 0
            player.died_by_revolver = True
            if player.is_human():
                print(f"\n  *** BANG! You pulled the trigger — it fires! Eliminated! ***")
            else:
                print(f"\n  *** BANG! {player.name} pulls the trigger — eliminated! ***")
        else:
            player.chips += revival_chips
            if player.is_human():
                print(f"\n  *** *CLICK* You survive the shot! +{revival_chips} chips. ***")
            else:
                print(f"\n  *** *CLICK* {player.name} survives! +{revival_chips} chips ***")

    # ── Revolver helpers ─────────────────────────────────────────────────────

    def _fire_revolver(self, shooter) -> bool:
        """Advance chamber and return True if the bullet fires."""
        fired = (shooter.gun_current_chamber == shooter.gun_bullet_chamber)
        shooter.gun_current_chamber = (shooter.gun_current_chamber + 1) % 6
        return fired

    def _reload_revolver(self, shooter):
        """After a kill: randomly place a new bullet, reset chamber to 0."""
        shooter.gun_bullet_chamber  = random.randint(0, 5)
        shooter.gun_current_chamber = 0

    # ── Lucky: draw 3, keep 2 ─────────────────────────────────────────────────

    def lucky_deal(self, player, deck) -> list:
        """Deal 3 cards to a Lucky player; return the 2 they keep."""
        three = deck.deal(3)

        if player.is_human():
            print(f"\n  [Lucky] You drew 3 cards — discard one:")
            for i, c in enumerate(three, 1):
                print(f"    {i}. {c}")
            raw = timed_input("  Discard which? [1/2/3, 10s]: ",
                              timeout=10.0, default='3')
            try:
                discard_idx = int(raw.strip()) - 1
                if not (0 <= discard_idx <= 2):
                    discard_idx = 2
            except ValueError:
                discard_idx = 2
        else:
            # Bot: keep the two cards with highest combined rank
            best_idx = 0
            best_sum = -1
            from itertools import combinations
            for combo in combinations(range(3), 2):
                s = three[combo[0]].rank + three[combo[1]].rank
                if s > best_sum:
                    best_sum = s
                    keep = set(combo)
            discard_idx = next(i for i in range(3) if i not in keep)

        kept    = [c for i, c in enumerate(three) if i != discard_idx]
        discard = three[discard_idx]
        deck.cards.append(discard)   # return discarded card to deck
        return kept

    # ── Lucky: prosecutor escape ──────────────────────────────────────────────

    def check_lucky_escape(self, dealer) -> bool:
        """Returns True if a Lucky dealer escapes prosecution consequences."""
        if dealer.role != RoleType.LUCKY:
            return False
        if random.random() < self.LUCKY_ESCAPE:
            print(f"\n  [Lucky] The prosecutor eyes {dealer.name}... "
                  f"then pockets the evidence and walks away.")
            return True
        return False

    # ── Shared helper ─────────────────────────────────────────────────────────

    def _lucky_immune(self, target, effect_desc: str) -> bool:
        if target.role != RoleType.LUCKY:
            return False
        if random.random() < self.LUCKY_IMMUNITY:
            print(f"\n  *** {target.name} is Lucky — immune to {effect_desc}! ***")
            return True
        return False
