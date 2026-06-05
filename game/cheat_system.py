import random
import sys
import time
from collections import namedtuple

from .card import Suit


# Per-hand shuffle time: (label, lo, hi, mean).
# Stronger hands require a longer, riskier shuffle.
# Honest range is 12.5–17.5 s (mean 15 s); overlap with honest shrinks as hands get stronger.
CheatHand = namedtuple('CheatHand', ['label', 'lo', 'hi', 'mean'])

CHEAT_HANDS = {
    # Each hand has a span of 3 s. Overall cheat range: 15–20 s.
    # Stronger hands sit higher in the range and overlap less with honest shuffles.
    'AA':  CheatHand('Pocket Aces',         17.0, 20.0, 18.5),
    'KK':  CheatHand('Pocket Kings',        16.5, 19.5, 18.0),
    'QQ':  CheatHand('Pocket Queens',       16.0, 19.0, 17.5),
    'JJ':  CheatHand('Pocket Jacks',        15.5, 18.5, 17.0),
    'TT':  CheatHand('Pocket Tens',         15.5, 18.5, 17.0),
    '99':  CheatHand('Pocket Nines',        15.0, 18.0, 16.5),
    '88':  CheatHand('Pocket Eights',       15.0, 18.0, 16.5),
    'AKs': CheatHand('Ace-King suited',     16.5, 19.5, 18.0),
    'AKo': CheatHand('Ace-King offsuit',    16.0, 19.0, 17.5),
    'AQs': CheatHand('Ace-Queen suited',    15.5, 18.5, 17.0),
    'AQo': CheatHand('Ace-Queen offsuit',   15.0, 18.0, 16.5),
    'KQs': CheatHand('King-Queen suited',   15.0, 18.0, 16.5),
}

# Derived compat aliases used by player.py
CHEAT_HAND_OPTIONS = list(CHEAT_HANDS.keys())
CHEAT_HAND_LABELS  = {k: v.label for k, v in CHEAT_HANDS.items()}

# Honest shuffle: right-skewed Beta(2, 3) on [12, 18].
# ~70% of draws fall in [12–15 s]; long tail reaches 18 s.
HONEST_RANGE  = (12.0, 18.0)
HONEST_ALPHA  = 2
HONEST_BETA   = 3

# Cheat hands still use a clamped Gaussian
SHUFFLE_STD   = 1.5

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

        if cheated:
            h = CHEAT_HANDS[chosen_hand]
            elapsed = max(h.lo, min(h.hi, random.gauss(h.mean, SHUFFLE_STD)))
        else:
            lo, hi = HONEST_RANGE
            elapsed = lo + random.betavariate(HONEST_ALPHA, HONEST_BETA) * (hi - lo)
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
        cheat_lo = min(h.lo for h in CHEAT_HANDS.values())
        cheat_hi = max(h.hi for h in CHEAT_HANDS.values())
        print(f"  Shuffle: {elapsed:.1f}s  "
              f"(honest {HONEST_RANGE[0]:.0f}–{HONEST_RANGE[1]:.0f}s / "
              f"suspicious {cheat_lo:.0f}–{cheat_hi:.0f}s)")
        print(f"  Calling costs {self.cost} chips.")

        accusers = []
        for p in players:
            if p is dealer or p.folded or p.chips < self.cost:
                continue
            if p.decide_to_accuse(elapsed, self.big_blind):
                p.chips -= self.cost
                accusers.append(p)
                print(f"  {p.name} calls the prosecutor!  (-{self.cost} chips)")
                break       # only the first player to call may prosecute
            elif not p.is_human():
                print(f"  {p.name} says nothing.")

        return accusers

    # ── Phase 3: resolution ───────────────────────────────────────────────────

    def resolve(self, accusers, dealer, cheated, escape: bool = False) -> bool:
        """
        Transfer chips between the single accuser and dealer.
        Returns True if the dealer was caught (caller must re-deal fairly).
        `escape` is True when a Lucky dealer avoids consequences.
        """
        if not accusers:
            return False

        acc = accusers[0]

        if escape:
            # Lucky role: refund the accuser, no penalty for dealer
            acc.chips += self.cost
            return False

        if cheated:
            print(f"\n  [Prosecutor] CHEATING CONFIRMED — {dealer.name} rigged the deck!")
            penalty = min(self.cost, dealer.chips)
            dealer.chips -= penalty
            acc.chips += self.cost + penalty    # fee refunded + penalty from dealer
            print(f"  {acc.name} gets back {self.cost} + takes {penalty} "
                  f"from {dealer.name}.  (dealer: {dealer.chips})")
            print(f"  Prosecutor re-shuffles and deals a fair hand to everyone.")
            return True
        else:
            print(f"\n  [Prosecutor] NOT CHEATING — false accusation.")
            dealer.chips += self.cost
            print(f"  {dealer.name} collects {self.cost} from {acc.name}.  "
                  f"(dealer: {dealer.chips})")
            return False

    # ── Deal the chosen hand from the deck ────────────────────────────────────

    _PAIR_RANK = {'AA': 14, 'KK': 13, 'QQ': 12, 'JJ': 11, 'TT': 10, '99': 9, '88': 8}
    _SUITED_RANKS  = {'AKs': (14, 13), 'AQs': (14, 12), 'KQs': (13, 12)}
    _OFFSUIT_RANKS = {'AKo': (14, 13), 'AQo': (14, 12)}

    def deal_cheat_hand(self, hand_name: str, deck) -> list:
        """Remove and return the chosen hand's two cards from the deck."""
        cards = self._select_cards(hand_name, deck)
        for c in cards:
            deck.cards.remove(c)
        return cards

    def _select_cards(self, hand_name: str, deck) -> list:
        if hand_name in self._PAIR_RANK:
            rank = self._PAIR_RANK[hand_name]
            return [c for c in deck.cards if c.rank == rank][:2]

        if hand_name in self._SUITED_RANKS:
            r1, r2 = self._SUITED_RANKS[hand_name]
            for suit in Suit:
                a = next((c for c in deck.cards if c.rank == r1 and c.suit == suit), None)
                b = next((c for c in deck.cards if c.rank == r2 and c.suit == suit), None)
                if a and b:
                    return [a, b]
            # No suited combo available — fall back to offsuit with same ranks

        # Offsuit (or suited fallback)
        r1, r2 = (self._SUITED_RANKS if hand_name in self._SUITED_RANKS
                  else self._OFFSUIT_RANKS)[hand_name]
        c1 = next((c for c in deck.cards if c.rank == r1), None)
        c2_diff = [c for c in deck.cards if c.rank == r2 and (not c1 or c.suit != c1.suit)]
        c2 = c2_diff[0] if c2_diff else next((c for c in deck.cards if c.rank == r2), None)
        return [c1, c2] if c1 and c2 else []

    # ── Internal ──────────────────────────────────────────────────────────────

    def _animate(self, name: str, duration: float):
        frames = ['|', '/', '-', '\\']
        start  = time.time()
        i = 0
        while time.time() - start < duration:
            print(f"\r  {name} is shuffling... [{frames[i % 4]}]", end='', flush=True)
            i += 1
            time.sleep(0.15)
