import random
from enum import Enum


class Suit(Enum):
    HEARTS = 'Hearts'
    DIAMONDS = 'Diamonds'
    CLUBS = 'Clubs'
    SPADES = 'Spades'


SUIT_SYMBOL = {'Hearts': '♥', 'Diamonds': '♦', 'Clubs': '♣', 'Spades': '♠'}
RANK_SYMBOL = {
    2: '2', 3: '3', 4: '4', 5: '5', 6: '6', 7: '7', 8: '8',
    9: '9', 10: 'T', 11: 'J', 12: 'Q', 13: 'K', 14: 'A'
}


class Card:
    def __init__(self, rank: int, suit: Suit):
        self.rank = rank  # 2–14, Ace = 14
        self.suit = suit

    def __repr__(self):
        return f"{RANK_SYMBOL[self.rank]}{SUIT_SYMBOL[self.suit.value]}"

    def __lt__(self, other):
        return self.rank < other.rank


class Deck:
    def __init__(self):
        self.reset()

    def reset(self):
        self.cards = [Card(rank, suit) for suit in Suit for rank in range(2, 15)]
        random.shuffle(self.cards)

    def deal(self, n=1):
        if n > len(self.cards):
            raise ValueError("Not enough cards left in deck")
        dealt, self.cards = self.cards[:n], self.cards[n:]
        return dealt
