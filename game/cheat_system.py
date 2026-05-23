import random
import sys
import time

from .card import Suit


CHEAT_HAND_OPTIONS = ['AA', 'KK', 'QQ', 'AKs', 'AKo']
CHEAT_HAND_LABELS = {
    'AA':  'Pocket Aces',
    'KK':  'Pocket Kings',
    'QQ':  'Pocket Queens',
    'AKs': 'Ace-King suited',
    'AKo': 'Ace-King offsuit',
}

# Shuffle durations shown to players (seconds)
HONEST_RANGE = (10.0, 14.9)
CHEAT_RANGE  = (15.0, 20.0)

# Real wall-clock scale so waits aren't painfully long
REAL_TIME_SCALE = 0.35


def timed_input(prompt: str, timeout: float, default: str = '') -> str:
    """Read a line from stdin within `timeout` seconds. Returns `default` on expiry."""
    print(prompt, end='', flush=True)
    try:
        import select as _sel
        ready, _, _ = _sel.select([sys.stdin], [], [], timeout)
        if ready:
            return sys.stdin.readline().rstrip('\n').strip()
        print(f"\n  [Time's up — using '{default}']")
        return default
    except Exception:
        # Non-TTY (tests, Windows): fall back to blocking input
        try:
            return input().strip()
        except EOFError:
            return default


class CheatSystem:
    def __init__(self, big_blind: int):
        self.big_blind = big_blind
        self.cost = 2 * big_blind       # chips to call the prosecutor

    # ── Phase 1: dealer shuffles ──────────────────────────────────────────────

    def shuffle_phase(self, dealer, deck) -> tuple:
        """
        Dealer secretly decides to cheat or shuffle honestly.
        Plays a real-time animation everyone can see.
        Returns (cheated: bool, display_elapsed: float, chosen_hand: str|None).
        Does NOT touch hole_cards or the deck yet.
        """
        print(f"\n  ── Shuffle Phase (Dealer: {dealer.name}) ──")
        cheated, chosen_hand = dealer.decide_to_cheat(deck)

        elapsed = (
            random.uniform(*CHEAT_RANGE)  if cheated
            else random.uniform(*HONEST_RANGE)
        )
        self._animate(dealer.name, elapsed * REAL_TIME_SCALE)
        print(f"\r  {dealer.name} finished shuffling in {elapsed:.1f}s.{' ' * 12}")

        return cheated, elapsed, chosen_hand

    # ── Phase 2: accusation window ────────────────────────────────────────────

    def accusation_phase(self, players, dealer, elapsed) -> list:
        """
        Each non-dealer player sees the shuffle time and may call the prosecutor.
        Returns list of accusers (their cost is deducted immediately).
        """
        print(f"\n  ── Prosecution Window ──")
        print(f"  Shuffle: {elapsed:.1f}s  "
              f"(honest {HONEST_RANGE[0]:.0f}–{HONEST_RANGE[1]:.0f}s / "
              f"suspicious {CHEAT_RANGE[0]:.0f}–{CHEAT_RANGE[1]:.0f}s)")
        print(f"  Calling costs {self.cost} chips.")

        accusers = []
        for p in players:
            if p is dealer or p.folded or p.chips < self.cost:
                continue
            if p.decide_to_accuse(elapsed, self.big_blind):
                p.chips -= self.cost
                accusers.append(p)
                print(f"  {p.name} calls the prosecutor!  (-{self.cost} chips)")
            elif not p.is_human():
                print(f"  {p.name} says nothing.")

        return accusers

    # ── Phase 3: resolution ───────────────────────────────────────────────────

    def resolve(self, accusers, dealer, cheated) -> bool:
        """
        Transfer chips between accusers and dealer.
        Returns True if the dealer was caught and must be force-folded.
        """
        if not accusers:
            return False

        if cheated:
            print(f"\n  [Prosecutor] CHEATING CONFIRMED — {dealer.name} rigged the deck!")
            for acc in accusers:
                penalty = min(self.cost, dealer.chips)
                dealer.chips -= penalty
                # accuser gets their fee back plus the penalty taken from dealer
                acc.chips += self.cost + penalty
                print(f"  {acc.name} gets back {self.cost} + takes {penalty} "
                      f"from {dealer.name}. (dealer: {dealer.chips})")
            return True
        else:
            print(f"\n  [Prosecutor] NOT CHEATING — false accusation(s).")
            for acc in accusers:
                dealer.chips += self.cost
                print(f"  {dealer.name} collects {self.cost} from {acc.name}. "
                      f"(dealer: {dealer.chips})")
            return False

    # ── Deal the chosen hand from the deck ────────────────────────────────────

    def deal_cheat_hand(self, hand_name: str, deck) -> list:
        """Remove and return the chosen hand's two cards from the deck."""
        cards = []

        if hand_name in ('AA', 'KK', 'QQ'):
            rank = {'AA': 14, 'KK': 13, 'QQ': 12}[hand_name]
            cards = [c for c in deck.cards if c.rank == rank][:2]

        elif hand_name == 'AKs':
            for suit in Suit:
                a = next((c for c in deck.cards if c.rank == 14 and c.suit == suit), None)
                k = next((c for c in deck.cards if c.rank == 13 and c.suit == suit), None)
                if a and k:
                    cards = [a, k]
                    break
            if not cards:
                hand_name = 'AKo'       # no suited combo available, fall through

        if hand_name == 'AKo' and not cards:
            a = next((c for c in deck.cards if c.rank == 14), None)
            ks = [c for c in deck.cards if c.rank == 13 and (not a or c.suit != a.suit)]
            k  = ks[0] if ks else next((c for c in deck.cards if c.rank == 13), None)
            if a and k:
                cards = [a, k]

        for c in cards:
            deck.cards.remove(c)

        return cards

    # ── Internal ──────────────────────────────────────────────────────────────

    def _animate(self, name: str, duration: float):
        frames = ['|', '/', '-', '\\']
        start  = time.time()
        i = 0
        while time.time() - start < duration:
            print(f"\r  {name} is shuffling... [{frames[i % 4]}]", end='', flush=True)
            i += 1
            time.sleep(0.15)
