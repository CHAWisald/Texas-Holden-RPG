import { useState } from 'react'

// Active ability per role (LUCKY's perks are passive → no button).
const ABILITY_BY_ROLE = { GUNNER: 'shoot', CURSED: 'curse' }

// The in-game controls. It calls the functions from App (startHand, shuffle,
// accuse, action, ability) — same endpoints, same request bodies as the old
// index.html. Which buttons show is gated by the phase + whose turn it is.
function ActionBar({
  state,
  activeId,
  startHand,
  shuffle,
  accuse,
  action,
  ability,
  cheatHands,
}) {
  // Local UI state. raiseAmount: a controlled input. target: who to shoot/curse.
  // armed: during a betting turn, whether the ability rides on the next action.
  // cheatHand: "" = honest shuffle, else a cheat-hand key to rig the deck.
  const [raiseAmount, setRaiseAmount] = useState(50)
  const [target, setTarget] = useState('')
  const [armed, setArmed] = useState(false)
  const [cheatHand, setCheatHand] = useState('')

  const human = state?.players?.find((p) => p.is_human) ?? null
  if (!state || !human) return null // no game yet → no controls

  const phase = state.phase
  const isMyTurn = human.id === activeId
  const isBetting = phase.endsWith('_BETTING') && isMyTurn
  const between = phase === 'WAITING' || phase === 'HAND_OVER'

  const canStart = phase === 'WAITING' || phase === 'HAND_OVER'
  const canShuffle = phase === 'SHUFFLE_PHASE' && isMyTurn
  const canAccuse = phase === 'ACCUSATION_PHASE' && isMyTurn
  const toCall = state.current_bet - human.street_bet

  // ── Ability gating (mirror of the old updateControls) ──────────────
  const abilityType = ABILITY_BY_ROLE[human.role] ?? null // 'shoot' | 'curse' | null
  const canUseAbility =
    !!abilityType &&
    (between || isBetting) &&
    human.chips > 0 &&
    !(abilityType === 'curse' && human.has_cursed)

  // Shoot price: 10 BB × 2^shots (self-shots are free but still bump the count).
  const shotCost = 10 * state.big_blind * 2 ** (human.bullets_used || 0)
  const abilityLabel = abilityType === 'shoot' ? `Shoot 🔫 ${shotCost}` : 'Curse 😈'
  const opponents = state.players.filter((p) => !p.is_human && p.chips > 0)

  let abilityText = abilityLabel
  if (isBetting) {
    abilityText = armed ? `${abilityLabel} armed — pick action` : `${abilityLabel} first…`
  }

  // A betting action, optionally firing the armed ability first. Identical body
  // to the old bet buttons (use_ability_first + ability_target_id). Acting also
  // disarms, so the ability never carries into a later turn.
  function doAction(actionType, amount = 0) {
    action({
      playerId: state.to_act[0],
      action: actionType,
      amount,
      useAbilityFirst: armed,
      abilityTargetId: armed ? target || null : null,
    })
    if (armed) setArmed(false)
  }

  // The ability button: during a betting turn it arms/disarms; between hands it
  // fires /ability immediately. Empty target = the role's default.
  function onAbilityClick() {
    if (isBetting) setArmed((a) => !a)
    else ability({ playerId: human.id, abilityType, targetId: target || null })
  }

  return (
    <div
      style={{
        display: 'flex',
        gap: '0.5rem',
        flexWrap: 'wrap',
        alignItems: 'center',
        justifyContent: 'center',
        margin: '1rem 0',
      }}
    >
      {canStart && (
        <button className="primary" onClick={() => startHand()}>
          Start Hand
        </button>
      )}

      {canShuffle && (
        <>
          <select
            value={cheatHand}
            onChange={(e) => setCheatHand(e.target.value)}
            title="Shuffle honestly, or pick a hand to rig"
          >
            <option value="">honest</option>
            {Object.entries(cheatHands).map(([key, info]) => (
              <option key={key} value={key}>
                {info.label} ({info.lo}–{info.hi}s)
              </option>
            ))}
          </select>
          <button
            onClick={() =>
              shuffle({
                dealerId: state.hand_active_ids[state.dealer_pos],
                cheated: cheatHand !== '',
                chosenHand: cheatHand || null,
              })
            }
          >
            Shuffle
          </button>
        </>
      )}

      {canAccuse && (
        <>
          <button
            onClick={() =>
              accuse({ playerId: state.accusation_order[0], accuses: true })
            }
          >
            Accuse
          </button>
          <button
            onClick={() =>
              accuse({ playerId: state.accusation_order[0], accuses: false })
            }
          >
            Pass
          </button>
        </>
      )}

      {/* Betting controls — shown only when it's my turn. */}
      {isBetting && (
        <>
          <span style={{ color: '#9aa3ad', fontSize: '0.85rem' }}>
            {toCall > 0
              ? `bet is ${state.current_bet} — ${toCall} to call`
              : 'no bet to you — check or bet'}
          </span>
          <button onClick={() => doAction('fold')}>Fold</button>
          <button onClick={() => doAction('check')} disabled={toCall > 0}>
            Check
          </button>
          <button onClick={() => doAction('call')}>
            Call{toCall > 0 ? ` ${toCall}` : ''}
          </button>
          <button onClick={() => doAction('raise', Number(raiseAmount) || 0)}>
            Raise
          </button>
          <input
            type="number"
            min={0}
            value={raiseAmount}
            onChange={(e) => setRaiseAmount(e.target.value)}
            title="Raise by — chips above the call amount"
            style={{ width: '5rem' }}
          />
          <button onClick={() => doAction('all-in')}>All-in</button>
        </>
      )}

      {/* Role ability — target picker + button. Between hands the button fires
          immediately; during a betting turn it ARMS for the next action. */}
      {canUseAbility && (
        <>
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">
              {abilityType === 'shoot'
                ? 'self (roulette: win 20BB or die)'
                : 'auto (chip leader)'}
            </option>
            {opponents.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <button
            onClick={onAbilityClick}
            style={{
              background: '#20838f',
              color: '#fff',
              ...(armed
                ? {
                    outline: '2px solid #e9c46a',
                    boxShadow: '0 0 12px rgba(233,196,106,0.6)',
                  }
                : {}),
            }}
          >
            {abilityText}
          </button>
        </>
      )}
    </div>
  )
}

export default ActionBar
