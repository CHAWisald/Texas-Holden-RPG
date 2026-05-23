from game.player import HumanPlayer, BotPlayer
from game.texas_holdem import TexasHoldem

BOT_NAMES = ["Alice", "Bob", "Charlie", "Diana", "Eve"]
BOT_STYLES = [
    ("Alice",   0.4),   # tight/passive
    ("Bob",     0.6),   # balanced
    ("Charlie", 0.8),   # loose/aggressive
    ("Diana",   0.5),   # balanced
    ("Eve",     0.3),   # very tight
]


def main():
    print("=" * 45)
    print("       Texas Hold'em Poker")
    print("=" * 45)

    # Get player name
    try:
        name = input("Enter your name: ").strip() or "Player"
    except (EOFError, KeyboardInterrupt):
        return

    # Get number of opponents
    while True:
        try:
            raw = input("Number of bot opponents (1–5): ").strip()
            n_bots = int(raw)
            if 1 <= n_bots <= 5:
                break
            print("Please enter a number between 1 and 5.")
        except ValueError:
            print("Invalid input.")
        except (EOFError, KeyboardInterrupt):
            return

    # Build player list
    human = HumanPlayer(name, chips=1000)
    bots = [
        BotPlayer(bot_name, chips=1000, aggression=agg)
        for bot_name, agg in BOT_STYLES[:n_bots]
    ]
    players = [human] + bots

    game = TexasHoldem(players, small_blind=10, big_blind=20)
    game.play()


if __name__ == "__main__":
    main()
