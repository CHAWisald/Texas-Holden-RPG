import './Card.css'

// The engine sends each card as { rank: 2–14, suit: "Hearts"|"Diamonds"|"Clubs"|"Spades" }.
// These lookups turn that data into what a human reads — same tables the old
// index.html used in cardEl().
const SUIT_SYMBOLS = { Hearts: '♥', Diamonds: '♦', Clubs: '♣', Spades: '♠' }
const RANK_LABELS = { 11: 'J', 12: 'Q', 13: 'K', 14: 'A' }

// A single playing card. `rank` and `suit` are its props — the inputs a
// parent passes in. Given the same props, it always renders the same card.
function Card({ rank, suit }) {
  const red = suit === 'Hearts' || suit === 'Diamonds'
  return (
    <div className={red ? 'card red' : 'card'}>
      <span className="rank">{RANK_LABELS[rank] || rank}</span>
      <span className="suit">{SUIT_SYMBOLS[suit] || suit}</span>
    </div>
  )
}

export default Card
