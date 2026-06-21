#!/usr/bin/env python3
"""Interactive terminal launcher for the legacy Texas Hold'em CLI.

Run it from a real terminal so the prompts can read your input:

    python play.py

You are seated with three bots. The human is the GUNNER by default so you
can try the revolver; the bots get random roles, matching the web UI.
"""
import random

from game.player import HumanPlayer, BotPlayer
from game.roles import RoleType
from game.texas_holdem import TexasHoldem

STARTING_CHIPS = 1000
SMALL_BLIND, BIG_BLIND = 25, 50


def main():
    you = HumanPlayer("You", STARTING_CHIPS)
    you.role = RoleType.GUNNER

    bots = [
        BotPlayer("Tex",   STARTING_CHIPS, aggression=0.3),
        BotPlayer("Doc",   STARTING_CHIPS, aggression=0.5),
        BotPlayer("Wyatt", STARTING_CHIPS, aggression=0.8),
    ]
    for b in bots:
        b.role = random.choice(list(RoleType))

    TexasHoldem([you, *bots], small_blind=SMALL_BLIND, big_blind=BIG_BLIND).play()


if __name__ == "__main__":
    main()
