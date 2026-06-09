"""
Tests for RoleSystem — all mechanics, no I/O.
Uses BotPlayer throughout (no timed_input calls).
random is patched deterministically wherever a specific outcome is required.
"""
import pytest
from unittest.mock import patch
from game.roles import RoleSystem, RoleType
from game.player import BotPlayer
from game.card import Card, Suit, Deck


# ── fixtures ──────────────────────────────────────────────────────────────────

BB = 20   # big blind used across all tests

@pytest.fixture
def rs():
    return RoleSystem(BB)

def bot(name='P', chips=1000, role=None):
    p = BotPlayer(name, chips)
    p.role = role
    return p

def gunner(name='G', chips=1000):
    return bot(name, chips, RoleType.GUNNER)

def cursed(name='C', chips=1000):
    return bot(name, chips, RoleType.CURSED)

def lucky(name='L', chips=1000):
    return bot(name, chips, RoleType.LUCKY)

def c(rank, suit='s'):
    s = {'h': Suit.HEARTS, 'd': Suit.DIAMONDS, 'c': Suit.CLUBS, 's': Suit.SPADES}
    return Card(rank, s[suit])


# ── revolver mechanics ────────────────────────────────────────────────────────

class TestRevolver:
    def test_click_on_non_bullet_chamber(self, rs):
        p = gunner()
        p.gun_bullet_chamber  = 3
        p.gun_current_chamber = 0
        assert rs._fire_revolver(p) is False

    def test_bang_on_bullet_chamber(self, rs):
        p = gunner()
        p.gun_bullet_chamber  = 0
        p.gun_current_chamber = 0
        assert rs._fire_revolver(p) is True

    def test_chamber_advances_after_fire(self, rs):
        p = gunner()
        p.gun_bullet_chamber  = 5
        p.gun_current_chamber = 2
        rs._fire_revolver(p)
        assert p.gun_current_chamber == 3

    def test_chamber_wraps_at_6(self, rs):
        p = gunner()
        p.gun_bullet_chamber  = 3
        p.gun_current_chamber = 5
        rs._fire_revolver(p)
        assert p.gun_current_chamber == 0

    def test_exactly_one_bang_in_six_pulls(self, rs):
        p = gunner()
        p.gun_bullet_chamber  = 2
        p.gun_current_chamber = 0
        results = [rs._fire_revolver(p) for _ in range(6)]
        assert results.count(True)  == 1
        assert results.count(False) == 5
        assert results[2] is True

    def test_reload_resets_chamber_to_zero(self, rs):
        p = gunner()
        p.gun_current_chamber = 4
        with patch('random.randint', return_value=3):
            rs._reload_revolver(p)
        assert p.gun_current_chamber == 0
        assert p.gun_bullet_chamber  == 3

    def test_reload_randomises_bullet(self, rs):
        p = gunner()
        positions = set()
        for pos in range(6):
            with patch('random.randint', return_value=pos):
                rs._reload_revolver(p)
            positions.add(p.gun_bullet_chamber)
        assert positions == {0, 1, 2, 3, 4, 5}


# ── _do_shoot ────────────────────────────────────────────────────────────────

class TestDoShoot:
    def test_chips_always_deducted_on_shoot(self, rs):
        shooter = gunner(chips=1000)
        target  = bot('T', chips=500)
        shooter.gun_bullet_chamber  = 5
        shooter.gun_current_chamber = 0   # chamber 0 → CLICK
        cost = BB * rs.GUNNER_BASE_BB
        rs._do_shoot(shooter, target, cost)
        assert shooter.chips == 1000 - cost

    def test_bullets_used_increments(self, rs):
        shooter = gunner(chips=1000)
        target  = bot('T', chips=500)
        shooter.gun_bullet_chamber  = 5
        shooter.gun_current_chamber = 0
        rs._do_shoot(shooter, target, BB * rs.GUNNER_BASE_BB)
        assert shooter.bullets_used == 1

    def test_click_leaves_target_alive(self, rs):
        shooter = gunner(chips=1000)
        target  = bot('T', chips=500)
        shooter.gun_bullet_chamber  = 5
        shooter.gun_current_chamber = 0   # miss
        rs._do_shoot(shooter, target, BB * rs.GUNNER_BASE_BB)
        assert target.chips == 500

    def test_bang_eliminates_target(self, rs):
        shooter = gunner(chips=1000)
        target  = bot('T', chips=500)
        shooter.gun_bullet_chamber  = 0
        shooter.gun_current_chamber = 0   # BANG
        rs._do_shoot(shooter, target, BB * rs.GUNNER_BASE_BB)
        assert target.chips == 0

    def test_bang_triggers_reload(self, rs):
        shooter = gunner(chips=1000)
        target  = bot('T', chips=500)
        shooter.gun_bullet_chamber  = 0
        shooter.gun_current_chamber = 0
        old_bullet = shooter.gun_bullet_chamber
        with patch('random.randint', return_value=4):
            rs._do_shoot(shooter, target, BB * rs.GUNNER_BASE_BB)
        assert shooter.gun_current_chamber == 0
        assert shooter.gun_bullet_chamber  == 4

    def test_lucky_immune_target_survives_bang(self, rs):
        shooter = gunner(chips=1000)
        target  = lucky('L', chips=500)
        shooter.gun_bullet_chamber  = 0
        shooter.gun_current_chamber = 0   # would be BANG
        # Force Lucky immunity to trigger
        with patch('random.random', return_value=0.10):   # < 0.30 → immune
            rs._do_shoot(shooter, target, BB * rs.GUNNER_BASE_BB)
        assert target.chips == 500   # survived despite BANG

    def test_non_lucky_not_immune(self, rs):
        shooter = gunner(chips=1000)
        target  = bot('T', chips=500, role=RoleType.CURSED)
        shooter.gun_bullet_chamber  = 0
        shooter.gun_current_chamber = 0
        rs._do_shoot(shooter, target, BB * rs.GUNNER_BASE_BB)
        assert target.chips == 0


# ── _do_shoot_self ────────────────────────────────────────────────────────────

class TestDoShootSelf:
    REVIVAL = BB * RoleSystem.DEVIL_LOAN_BB

    def test_click_adds_revival_chips(self, rs):
        p = gunner(chips=100)
        p.gun_bullet_chamber  = 5
        p.gun_current_chamber = 0   # CLICK
        rs._do_shoot_self(p, self.REVIVAL)
        assert p.chips == 100 + self.REVIVAL

    def test_bang_sets_chips_to_zero(self, rs):
        p = gunner(chips=100)
        p.gun_bullet_chamber  = 0
        p.gun_current_chamber = 0   # BANG
        rs._do_shoot_self(p, self.REVIVAL)
        assert p.chips == 0

    def test_bang_sets_died_by_revolver(self, rs):
        p = gunner(chips=100)
        p.gun_bullet_chamber  = 0
        p.gun_current_chamber = 0
        rs._do_shoot_self(p, self.REVIVAL)
        assert p.died_by_revolver is True

    def test_click_does_not_set_died_by_revolver(self, rs):
        p = gunner(chips=100)
        p.gun_bullet_chamber  = 5
        p.gun_current_chamber = 0
        rs._do_shoot_self(p, self.REVIVAL)
        assert p.died_by_revolver is False

    def test_bullets_used_increments(self, rs):
        p = gunner(chips=100)
        p.gun_bullet_chamber  = 5
        p.gun_current_chamber = 0
        rs._do_shoot_self(p, self.REVIVAL)
        assert p.bullets_used == 1


# ── _gunner_bust ──────────────────────────────────────────────────────────────

class TestGunnerBust:
    def test_died_by_revolver_blocks_revival(self, rs):
        p = gunner(chips=0)
        p.died_by_revolver = True
        result = rs._gunner_bust(p)
        assert result is False
        assert p.chips == 0

    def test_click_revives_bot(self, rs):
        p = gunner(chips=0)
        p.gun_bullet_chamber  = 5
        p.gun_current_chamber = 0   # CLICK
        result = rs._gunner_bust(p)
        assert result is True
        assert p.chips == BB * RoleSystem.DEVIL_LOAN_BB

    def test_bang_eliminates_bot(self, rs):
        p = gunner(chips=0)
        p.gun_bullet_chamber  = 0
        p.gun_current_chamber = 0   # BANG
        result = rs._gunner_bust(p)
        assert result is False
        assert p.died_by_revolver is True

    def test_bang_does_not_add_chips(self, rs):
        p = gunner(chips=0)
        p.gun_bullet_chamber  = 0
        p.gun_current_chamber = 0
        rs._gunner_bust(p)
        assert p.chips == 0

    def test_bullets_used_increments_on_bust(self, rs):
        p = gunner(chips=0)
        p.gun_bullet_chamber  = 5
        p.gun_current_chamber = 0
        rs._gunner_bust(p)
        assert p.bullets_used == 1


# ── handle_bust ───────────────────────────────────────────────────────────────

class TestHandleBust:
    def test_lucky_not_revived(self, rs):
        p = lucky(chips=0)
        assert rs.handle_bust(p) is False

    def test_no_role_not_revived(self, rs):
        p = bot(chips=0)
        assert rs.handle_bust(p) is False

    def test_gunner_routes_to_gunner_bust(self, rs):
        p = gunner(chips=0)
        p.gun_bullet_chamber  = 5
        p.gun_current_chamber = 0
        assert rs.handle_bust(p) is True   # CLICK → revived

    def test_cursed_routes_to_cursed_bust(self, rs):
        p = cursed(chips=0)
        with patch('random.randint', return_value=6):   # 6-hand period
            result = rs.handle_bust(p)
        assert result is True
        assert p.is_devil is True


# ── _cursed_bust ──────────────────────────────────────────────────────────────

class TestCursedBust:
    def test_bot_accepts_deal(self, rs):
        p = cursed(chips=0)
        with patch('random.randint', return_value=5):
            result = rs._cursed_bust(p)
        assert result is True
        assert p.chips == BB * RoleSystem.DEVIL_LOAN_BB
        assert p.devil_debt == BB * RoleSystem.DEVIL_DEBT_BB
        assert p.is_devil is True

    def test_period_in_range(self, rs):
        p = cursed(chips=0)
        rs._cursed_bust(p)
        assert RoleSystem.CURSE_MIN <= p.devil_hands <= 8   # 5–8 hands

    def test_second_bust_while_in_debt_rejected(self, rs):
        p = cursed(chips=0)
        p.devil_debt = 100
        result = rs._cursed_bust(p)
        assert result is False
        assert p.chips == 0


# ── tick_devil_debts ──────────────────────────────────────────────────────────

class TestTickDevilDebts:
    def _make_devil(self, chips=2000, debt=500, hands=3):
        p = cursed(chips=chips)
        p.is_devil    = True
        p.devil_debt  = debt
        p.devil_hands = hands
        return p

    def test_non_devil_skipped(self, rs):
        p = cursed(chips=1000)   # not in devil state
        rs.tick_devil_debts([p])
        assert p.devil_hands == 0   # unchanged

    def test_countdown_decrements(self, rs):
        p = self._make_devil(hands=3)
        rs.tick_devil_debts([p])
        assert p.devil_hands == 2

    def test_repayment_on_deadline(self, rs):
        p = self._make_devil(chips=1000, debt=500, hands=1)
        rs.tick_devil_debts([p])
        assert p.chips == 500
        assert p.devil_debt == 0
        assert p.is_devil is False

    def test_default_on_insufficient_chips(self, rs):
        p = self._make_devil(chips=100, debt=500, hands=1)
        rs.tick_devil_debts([p])
        assert p.chips == 0
        assert p.devil_debt == 0
        assert p.is_devil is False

    def test_no_action_before_deadline(self, rs):
        p = self._make_devil(chips=100, debt=500, hands=2)
        rs.tick_devil_debts([p])
        assert p.chips == 100   # untouched
        assert p.devil_debt == 500


# ── offer_curse_ability ───────────────────────────────────────────────────────

class TestOfferCurseAbility:
    def test_already_cursed_no_action(self, rs):
        p = cursed()
        p.has_cursed = True
        target = bot('T', chips=500)
        rs.offer_curse_ability(p, [p, target])
        assert target.curse_hands_left == 0

    def test_no_targets_no_action(self, rs):
        p = cursed()
        rs.offer_curse_ability(p, [p])   # no valid targets
        assert p.has_cursed is False

    def test_can_curse_without_devil_state(self, rs):
        p = cursed()
        p.is_devil = False   # not in devil state — should still work
        target = bot('T', chips=500)
        with patch('random.random', return_value=0.10):   # < 0.25 → curse fires
            rs.offer_curse_ability(p, [p, target])
        assert p.has_cursed is True

    def test_bot_curses_richest_target(self, rs):
        p = cursed()
        rich  = bot('Rich',  chips=2000)
        poor  = bot('Poor',  chips=100)
        with patch('random.random', return_value=0.10):
            rs.offer_curse_ability(p, [p, rich, poor])
        assert rich.curse_hands_left > 0
        assert poor.curse_hands_left == 0

    def test_has_cursed_set_after_use(self, rs):
        p = cursed()
        target = bot('T', chips=500)
        with patch('random.random', return_value=0.10):
            rs.offer_curse_ability(p, [p, target])
        assert p.has_cursed is True

    def test_curse_duration_in_range(self, rs):
        p = cursed()
        target = bot('T', chips=500)
        with patch('random.random', return_value=0.10):
            rs.offer_curse_ability(p, [p, target])
        assert RoleSystem.CURSE_MIN <= target.curse_hands_left <= RoleSystem.CURSE_MAX

    def test_lucky_target_may_be_immune(self, rs):
        p = cursed()
        target = lucky('L', chips=500)
        # Force immunity
        with patch('random.random', return_value=0.05):   # 0.05 < 0.25 curse AND < 0.30 immune
            rs.offer_curse_ability(p, [p, target])
        # has_cursed=True (ability used) but curse didn't land due to immunity
        assert p.has_cursed is True
        assert target.curse_hands_left == 0


# ── apply_victim_curse ────────────────────────────────────────────────────────

class TestApplyVictimCurse:
    def test_no_effect_when_zero_hands_left(self, rs):
        p = bot('V', chips=500)
        p.curse_hands_left = 0
        p.hole_cards = [c(14), c(13)]
        deck = Deck()
        rs.apply_victim_curse(p, deck)
        assert p.hole_cards[0].rank == 14   # unchanged

    def test_decrements_hands_left(self, rs):
        p = bot('V', chips=500)
        p.curse_hands_left = 3
        deck = Deck()
        # Remove cards dealt to the player from deck first
        p.hole_cards = deck.deal(2)
        with patch('random.random', return_value=0.40):   # downgrade path
            rs.apply_victim_curse(p, deck)
        assert p.curse_hands_left == 2

    def test_curse_lifted_at_zero(self, rs, capsys):
        p = bot('V', chips=500)
        p.curse_hands_left = 1
        deck = Deck()
        p.hole_cards = deck.deal(2)
        with patch('random.random', return_value=0.40):
            rs.apply_victim_curse(p, deck)
        assert p.curse_hands_left == 0
        out = capsys.readouterr().out
        assert 'Curse lifted' in out or 'curse' in out.lower()


# ── detect_bluff_reward ───────────────────────────────────────────────────────

class TestDetectBluffReward:
    """Only activates for human Cursed players in devil state — bots excluded."""

    def _human_devil(self, debt=500):
        from game.player import HumanPlayer
        p = HumanPlayer('H', chips=1000)
        p.role       = RoleType.CURSED
        p.is_devil   = True
        p.devil_debt = debt
        return p

    def _community(self):
        # 2 7 9 Q K — no consecutive run long enough to form a straight with most hole cards
        return [c(2,'h'), c(7,'d'), c(9,'s'), c(12,'c'), c(13,'h')]

    def test_bot_gets_no_reward(self, rs):
        p = cursed(chips=1000)
        p.is_devil   = True
        p.devil_debt = 500
        p.hole_cards = [c(4,'s'), c(11,'d')]   # K Q J 9 7 = High Card
        rs.detect_bluff_reward(p, self._community())
        assert p.devil_debt == 500   # bots are excluded — unchanged

    def test_non_devil_no_reward(self, rs):
        p = self._human_devil()
        p.is_devil   = False
        p.hole_cards = [c(4,'s'), c(11,'d')]
        rs.detect_bluff_reward(p, self._community())
        assert p.devil_debt == 500

    def test_high_card_forgives_5bb(self, rs):
        p = self._human_devil(debt=500)
        # hole 4 J + community 2 7 9 Q K → best 5: K Q J 9 7 = High Card
        p.hole_cards = [c(4,'s'), c(11,'d')]
        rs.detect_bluff_reward(p, self._community())
        assert p.devil_debt == 500 - 5 * BB

    def test_one_pair_forgives_5bb(self, rs):
        p = self._human_devil(debt=500)
        # hole J J + community 2 7 9 Q K → J J K Q 9 = One Pair
        p.hole_cards = [c(11,'s'), c(11,'d')]
        rs.detect_bluff_reward(p, self._community())
        assert p.devil_debt == 500 - 5 * BB

    def test_two_pair_no_reward(self, rs):
        p = self._human_devil(debt=500)
        # hole 9 7 + community 2 7 9 Q K → 9 9 7 7 K = Two Pair
        p.hole_cards = [c(9,'h'), c(7,'c')]
        rs.detect_bluff_reward(p, self._community())
        assert p.devil_debt == 500   # strong hand → no reward

    def test_debt_cleared_sets_is_devil_false(self, rs):
        p = self._human_devil(debt=5 * BB)   # exactly one forgiveness worth
        p.hole_cards = [c(4,'s'), c(11,'d')]
        rs.detect_bluff_reward(p, self._community())
        assert p.devil_debt == 0
        assert p.is_devil is False

    def test_debt_does_not_go_negative(self, rs):
        p = self._human_devil(debt=10)   # less than 5BB forgiveness
        p.hole_cards = [c(4,'s'), c(11,'d')]
        rs.detect_bluff_reward(p, self._community())
        assert p.devil_debt == 0


# ── lucky_deal ────────────────────────────────────────────────────────────────

class TestLuckyDeal:
    def test_returns_two_cards(self, rs):
        p = lucky()
        deck = Deck()
        kept = rs.lucky_deal(p, deck)
        assert len(kept) == 2

    def test_bot_keeps_highest_rank_sum(self, rs):
        from game.card import Card
        p = lucky()
        deck = Deck()
        # Manually stack the top 3 cards: 2, 7, Ace
        two  = Card(2,  Suit.CLUBS)
        seven= Card(7,  Suit.HEARTS)
        ace  = Card(14, Suit.SPADES)
        deck.cards = [two, seven, ace] + deck.cards  # put them at front
        kept = rs.lucky_deal(p, deck)
        kept_ranks = sorted(c.rank for c in kept)
        # Bot keeps best 2: 7+14=21 > 2+14=16 > 2+7=9
        assert 14 in kept_ranks and 7 in kept_ranks

    def test_discarded_card_returned_to_deck(self, rs):
        p = lucky()
        deck = Deck()
        initial_size = len(deck.cards)
        rs.lucky_deal(p, deck)
        # 3 dealt, 1 returned → net -2
        assert len(deck.cards) == initial_size - 2


# ── check_lucky_escape ────────────────────────────────────────────────────────

class TestCheckLuckyEscape:
    def test_non_lucky_never_escapes(self, rs):
        p = gunner()
        with patch('random.random', return_value=0.01):
            assert rs.check_lucky_escape(p) is False

    def test_lucky_escapes_when_random_below_threshold(self, rs):
        p = lucky()
        with patch('random.random', return_value=0.10):   # < 0.30
            assert rs.check_lucky_escape(p) is True

    def test_lucky_does_not_escape_when_above_threshold(self, rs):
        p = lucky()
        with patch('random.random', return_value=0.50):   # >= 0.30
            assert rs.check_lucky_escape(p) is False


# ── _lucky_immune ─────────────────────────────────────────────────────────────

class TestLuckyImmune:
    def test_non_lucky_not_immune(self, rs):
        p = bot('T', chips=500, role=RoleType.GUNNER)
        with patch('random.random', return_value=0.01):
            assert rs._lucky_immune(p, 'test') is False

    def test_lucky_immune_below_threshold(self, rs):
        p = lucky()
        with patch('random.random', return_value=0.20):
            assert rs._lucky_immune(p, 'test') is True

    def test_lucky_not_immune_above_threshold(self, rs):
        p = lucky()
        with patch('random.random', return_value=0.40):
            assert rs._lucky_immune(p, 'test') is False


# ── offer_shoot_ability ───────────────────────────────────────────────────────

class TestOfferShootAbility:
    def test_non_gunner_no_action(self, rs):
        p = cursed(chips=1000)
        target = bot('T', chips=500)
        rs.offer_shoot_ability(p, [p, target])
        assert target.chips == 500

    def test_bot_shoots_richest_target(self, rs):
        shooter = gunner(chips=1000)
        shooter.gun_bullet_chamber  = 0
        shooter.gun_current_chamber = 0   # BANG
        rich = bot('Rich', chips=2000)
        poor = bot('Poor', chips=100)
        cost = rs.GUNNER_BASE_BB * BB * (2 ** shooter.bullets_used)
        # Force bot to decide to shoot (roll < 0.15)
        with patch('random.random', return_value=0.10):
            rs.offer_shoot_ability(shooter, [shooter, rich, poor])
        assert rich.chips == 0   # richest was shot dead

    def test_bot_does_not_shoot_without_chips(self, rs):
        shooter = gunner(chips=10)   # can't afford cost=200
        target = bot('T', chips=500)
        # Force bot roll to 0.10 (would shoot if affordable)
        with patch('random.random', return_value=0.10):
            rs.offer_shoot_ability(shooter, [shooter, target])
        # Bot is in the "desperate self-shoot" branch, not opponent shoot
        # Target should NOT be eliminated (bot can't afford opponent shot)
        assert target.chips == 500

    def test_cost_doubles_each_shot(self, rs):
        shooter = gunner(chips=1000)
        shooter.gun_bullet_chamber  = 5
        shooter.gun_current_chamber = 0
        target = bot('T', chips=500)
        cost1 = rs.GUNNER_BASE_BB * BB * (2 ** 0)   # 200
        cost2 = rs.GUNNER_BASE_BB * BB * (2 ** 1)   # 400
        # First shot
        with patch('random.random', return_value=0.10):
            rs.offer_shoot_ability(shooter, [shooter, target])
        assert shooter.chips == 1000 - cost1
        # Second shot cost
        assert rs.GUNNER_BASE_BB * BB * (2 ** shooter.bullets_used) == cost2
