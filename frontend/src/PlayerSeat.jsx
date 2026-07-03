import { motion } from 'motion/react'
import './PlayerSeat.css'
import HoleCards from './HoleCards.jsx'

// Standard position names by seat offset from the dealer button, per table
// size — copied from the old index.html positionNames().
function positionNames(n) {
  if (n === 2) return ['BTN/SB', 'BB']
  const mids = {
    1: ['UTG'],
    2: ['UTG', 'CO'],
    3: ['UTG', 'MP', 'CO'],
    4: ['UTG', 'MP', 'HJ', 'CO'],
    5: ['UTG', 'UTG+1', 'MP', 'HJ', 'CO'],
    6: ['UTG', 'UTG+1', 'UTG+2', 'MP', 'HJ', 'CO'],
  }
  return ['BTN', 'SB', 'BB', ...(mids[n - 3] || [])]
}

// One player's seat. `player` is its data; `index`/`total` place it on the
// ellipse; `dealerPos`/`handActiveIds` drive the dealer + blind markers.
function PlayerSeat({
  player,
  index,
  total,
  dealerPos,
  handActiveIds,
  isActive,
  lastAction,
  handResult,
  phase,
  isCursed,
  curseKey,
}) {
  // Ellipse placement: seat 0 bottom-centre, the rest evenly clockwise. Wider
  // than tall, and a touch tighter vertically so the bottom (human) seat stays
  // inside the felt with room for hole cards — clear of the action bar below.
  const angle = Math.PI / 2 + (2 * Math.PI * index) / total
  const left = `${50 + 40 * Math.cos(angle)}%`
  const top = `${50 + 34 * Math.sin(angle)}%`

  // Dealer button + position tag only exist once a hand is dealt
  // (hand_active_ids is empty before that). Same logic as the old seatEl:
  // a player's position is its offset from the dealer around the active seats.
  const ids = handActiveIds ?? []
  const seatIdx = ids.indexOf(player.id)
  const dealt = ids.length > 0 && seatIdx !== -1
  const isDealer = dealt && ids[dealerPos] === player.id
  const position = dealt
    ? positionNames(ids.length)[(seatIdx - dealerPos + ids.length) % ids.length]
    : null

  // Hand-over results (set by the engine at HAND_OVER, cleared next hand).
  const result = handResult
  const showdown = !!result && result.type === 'showdown'
  const isWinner = !!result && result.winner_ids.includes(player.id)
  // Your own cards always; at showdown, every still-in (scored) player's cards.
  const reveal = player.is_human || (showdown && player.id in result.all_hands)
  const handName = showdown ? result.all_hands[player.id] : null
  const winnings = isWinner ? (showdown ? result.winnings[player.id] : result.pot) : 0
  const refund = showdown && result.refunds ? result.refunds[player.id] || 0 : 0

  // Chips committed this street, as a chip beside the seat. Blinds post before
  // SHUFFLE/ACCUSATION so those count; street_bet is stale once the hand ends.
  const inHand =
    phase === 'SHUFFLE_PHASE' ||
    phase === 'ACCUSATION_PHASE' ||
    (!!phase && phase.endsWith('_BETTING'))

  const className =
    'seat' +
    (player.is_human ? ' me' : '') +
    (isActive ? ' active' : '') +
    (player.folded ? ' folded' : '') +
    (isWinner ? ' winner' : '')

  return (
    <div className={className} style={{ left, top }}>
      {/* Curse pulse: a purple glow that throbs over the victim's seat. Same
          Framer Motion pattern as ShootFlash — key change replays it. */}
      {isCursed && (
        <motion.div
          key={curseKey}
          initial={{ opacity: 0 }}
          animate={{ opacity: [0, 1, 0, 1, 0] }}
          transition={{ duration: 1.2, times: [0, 0.18, 0.5, 0.72, 1] }}
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: 12,
            boxShadow: '0 0 16px 5px rgba(176, 102, 224, 0.85)',
            background: 'rgba(176, 102, 224, 0.18)',
            pointerEvents: 'none',
          }}
        />
      )}
      {position && <div className="pos-tag">{position}</div>}
      {isDealer && (
        <div className="dealer-btn" title="Dealer">
          D
        </div>
      )}
      {inHand && player.street_bet > 0 && (
        <div className="bet-chip">{player.street_bet}</div>
      )}

      {/* Hole cards: yours always; opponents only when revealed at showdown. */}
      {reveal && <HoleCards cards={player.hole_cards} />}

      <div className="seat-name">{player.name}</div>

      {player.role && (
        <div className={`seat-role ${player.role.toLowerCase()}`}>
          {player.role}
        </div>
      )}

      <div className="seat-chips">{player.chips} chips</div>

      {/* Last action this street ("call 40", "raise to 80", …) from events. */}
      {lastAction && <div className="seat-action">{lastAction}</div>}
      {/* Showdown name + winnings/refund. */}
      {handName && <div className="hand-name">{handName}</div>}
      {isWinner && <div className="seat-win">wins +{winnings}</div>}
      {refund > 0 && <div className="seat-refund">returned +{refund}</div>}
    </div>
  )
}

export default PlayerSeat
