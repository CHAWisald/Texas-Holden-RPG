import random

from game.player import HumanPlayer, BotPlayer
from game.texas_holdem import TexasHoldem
from game.roles import RoleType, ROLE_DESCRIPTIONS

BOT_STYLES = [
    ("Alice",   0.4),
    ("Bob",     0.6),
    ("Charlie", 0.8),
    ("Diana",   0.5),
    ("Eve",     0.3),
]

ALL_ROLES = [RoleType.CURSED, RoleType.GUNNER, RoleType.LUCKY]


def pick_role() -> RoleType:
    print("\n" + "=" * 45)
    print("  Choose your role")
    print("=" * 45)
    for i, role in enumerate(ALL_ROLES, 1):
        print(f"\n  {i}. {role.value}")
        for line in ROLE_DESCRIPTIONS[role].split('\n'):
            print(f"     {line}")
    print()
    while True:
        try:
            raw = input("  Your choice [1/2/3]: ").strip()
            idx = int(raw) - 1
            if 0 <= idx <= 2:
                return ALL_ROLES[idx]
        except (ValueError, EOFError, KeyboardInterrupt):
            pass
        print("  Please enter 1, 2, or 3.")


def main():
    print("=" * 45)
    print("       Texas Hold'em Poker")
    print("=" * 45)

    try:
        name = input("Enter your name: ").strip() or "Player"
    except (EOFError, KeyboardInterrupt):
        return

    while True:
        try:
            raw    = input("Number of bot opponents (1–5): ").strip()
            n_bots = int(raw)
            if 1 <= n_bots <= 5:
                break
            print("Please enter a number between 1 and 5.")
        except ValueError:
            print("Invalid input.")
        except (EOFError, KeyboardInterrupt):
            return

    human_role = pick_role()

    human      = HumanPlayer(name, chips=1000)
    human.role = human_role
    print(f"\n  You are playing as: {human_role.value}")

    bots = []
    for bot_name, agg in BOT_STYLES[:n_bots]:
        bot      = BotPlayer(bot_name, chips=1000, aggression=agg)
        bot.role = random.choice(ALL_ROLES)
        bots.append(bot)

    print("\n  Bot roles:")
    for bot in bots:
        print(f"    {bot.name:<10} {bot.role.value}")

    players = [human] + bots
    game    = TexasHoldem(players, small_blind=10, big_blind=20)
    game.play()


if __name__ == "__main__":
    main()
