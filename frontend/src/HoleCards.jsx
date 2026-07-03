import './HoleCards.css'
import Card from './Card.jsx'

// A row of hole cards, built from <Card>. `cards` is an array of { rank, suit }.
// Renders nothing when there are no cards (e.g. before a hand is dealt).
function HoleCards({ cards }) {
  if (!cards || cards.length === 0) return null
  return (
    <div className="hole-cards">
      {cards.map((c) => (
        <Card key={`${c.rank}-${c.suit}`} rank={c.rank} suit={c.suit} />
      ))}
    </div>
  )
}

export default HoleCards
