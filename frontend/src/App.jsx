import { useState, useEffect, useRef } from 'react'
import { motion } from 'motion/react'
import './App.css'
import Card from './Card.jsx'
import PlayerSeat from './PlayerSeat.jsx'
import ActionBar from './ActionBar.jsx'
import EventLog from './EventLog.jsx'
import AnnounceBanner from './AnnounceBanner.jsx'
import ShootFlash from './ShootFlash.jsx'

// Your FastAPI backend. In dev (`npm run dev`, Vite on :5173) it lives on
// :8000 — the backend's CORS allowlist covers :5173 for exactly this. In the
// production build FastAPI serves this app itself, so '' = same origin.
const API = import.meta.env.DEV ? 'http://localhost:8000' : ''

// How often to poll for game-state updates while a game is in progress.
const POLL_MS = 2000

// Pot pills shown in the middle of the felt.
const POT_PILL = {
  padding: '0.28rem 1rem',
  fontWeight: 'bold',
  color: '#e9c46a',
  background: 'rgba(0,0,0,0.5)',
  border: '1px solid rgba(233,196,106,0.45)',
  borderRadius: 999,
  boxShadow: 'inset 0 1px 4px rgba(0,0,0,0.5)',
  whiteSpace: 'nowrap',
}
const SIDE_POT_PILL = {
  ...POT_PILL,
  color: '#bcae8a',
  border: '1px solid rgba(188,174,138,0.4)',
}

// The exact players your old index.html sends. The human takes no role for
// now (we'll add a picker later); each bot draws a random one, like before.
const DEFAULT_PLAYERS = [
  { id: 'human', name: 'You',   is_human: true,  chips: 1000 },
  { id: 'bot1',  name: 'Tex',   is_human: false, chips: 1000, aggression: 0.3 },
  { id: 'bot2',  name: 'Doc',   is_human: false, chips: 1000, aggression: 0.5 },
  { id: 'bot3',  name: 'Wyatt', is_human: false, chips: 1000, aggression: 0.8 },
]
const ROLES = ['CURSED', 'GUNNER', 'LUCKY']

function rollPlayers(humanRole) {
  return DEFAULT_PLAYERS.map((p) => ({
    ...p,
    role: p.is_human
      ? humanRole || null
      : ROLES[Math.floor(Math.random() * ROLES.length)],
  }))
}

// Which player is on the clock right now, derived purely from the state —
// ported from the old index.html activePlayerId(). null = nobody's turn
// (WAITING, HAND_OVER, GAME_OVER).
function activePlayerId(state) {
  if (!state) return null
  if (state.phase === 'SHUFFLE_PHASE') return state.hand_active_ids[state.dealer_pos]
  if (state.phase === 'ACCUSATION_PHASE') return state.accusation_order[0]
  if (state.phase.endsWith('_BETTING')) return state.to_act[0]
  return null
}

// Fold the event stream into per-seat "last action this street" labels, the
// same buckets the old index.html processEvents() used: street/hand boundaries
// clear the labels; betting events set them. `prev` is carried in so a label
// from an earlier batch in the same street survives. Returns `prev` unchanged
// (same reference) when nothing relevant happened, so React can bail out.
function applyEventLabels(prev, events) {
  let next = prev
  const set = (pid, label) => {
    if (next === prev) next = { ...prev } // copy lazily, only on first change
    next[pid] = label
  }
  for (const ev of events) {
    switch (ev.type) {
      case 'hand_start':
      case 'preflop_start':
      case 'street_start':
        next = {} // new street → clear stale labels
        break
      case 'fold':      set(ev.player_id, 'fold'); break
      case 'check':     set(ev.player_id, 'check'); break
      case 'call':      set(ev.player_id, `call ${ev.amount}`); break
      case 'raise':     set(ev.player_id, `raise to ${ev.amount}`); break
      case 'all_in':    set(ev.player_id, `all-in ${ev.amount}`); break
      case 'dead_fold': set(ev.player_id, 'fold (no chips)'); break
      default: break
    }
  }
  return next
}

// ── Network helpers (no React state — pure functions) ─────────────────
// api(): do a fetch, throw a readable error on any failure, return JSON.
async function api(path, options = {}) {
  let resp
  try {
    resp = await fetch(API + path, options)
  } catch (err) {
    throw new Error(
      `Could not reach ${API}. Is the backend running (fastapi dev main.py)? ${err.message}`,
      { cause: err },
    )
  }
  if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`)
  return resp.json()
}

// post(): api() for POST endpoints. Body is optional — /start-hand takes none.
function post(path, body) {
  const options = { method: 'POST' }
  if (body !== undefined) {
    options.headers = { 'Content-Type': 'application/json' }
    options.body = JSON.stringify(body)
  }
  return api(path, options)
}

function App() {
  // ── Centralized game state (the single source of truth) ─────────────
  // Everything the UI shows is derived from these. Child components will
  // later receive them (and the action functions below) as props.
  //   gameState — the last full state object the server returned (null = none)
  //   gameId    — the current game's id, reused by every later call
  //   error     — the last error message to show ("" = none)
  const [gameState, setGameState] = useState(null)
  const [gameId, setGameId] = useState(null)
  const [error, setError] = useState('')
  // Per-seat last-action labels, derived from the event stream (see effect).
  const [lastActions, setLastActions] = useState({})
  const [role, setRole] = useState('') // human's chosen role for the next game
  const [cheatHands, setCheatHands] = useState({}) // /cheat-hands reference data

  // Shared runner: clear errors, await one endpoint call, store the new
  // state, and surface any failure in `error`. Returns the state (or
  // undefined on error). This is the one place that does setGameState/
  // setError, so every endpoint function below stays a clean one-liner.
  async function apply(call) {
    setError('')
    try {
      const state = await call()
      setGameState(state)
      return state
    } catch (err) {
      setError(err.message)
    }
  }

  // ── One function per backend endpoint ───────────────────────────────
  // POST /games — create a game, then remember its id for later calls.
  function newGame() {
    setLastActions({}) // drop any labels from a previous game
    apply(async () => {
      const state = await post('/games', {
        players: rollPlayers(role),
        small_blind: 25,
        big_blind: 50,
      })
      setGameId(state.game_id)
      return state
    })
  }

  // GET /games/{game_id} — re-fetch the current game's state.
  function refresh() {
    apply(() => api(`/games/${gameId}`))
  }

  // POST /games/{game_id}/start-hand — begin the next hand (no body).
  function startHand() {
    apply(() => post(`/games/${gameId}/start-hand`))
  }

  // POST /games/{game_id}/shuffle — dealer commits the shuffle decision.
  function shuffle({ dealerId, cheated, chosenHand = null }) {
    apply(() =>
      post(`/games/${gameId}/shuffle`, {
        dealer_id: dealerId,
        cheated,
        chosen_hand: chosenHand,
      }),
    )
  }

  // POST /games/{game_id}/accuse — a player accuses the dealer (or passes).
  function accuse({ playerId, accuses }) {
    apply(() =>
      post(`/games/${gameId}/accuse`, { player_id: playerId, accuses }),
    )
  }

  // POST /games/{game_id}/action — a betting action (fold/check/call/raise/all-in).
  function action({
    playerId,
    action: actionType,
    amount = 0,
    useAbilityFirst = false,
    abilityTargetId = null,
  }) {
    apply(() =>
      post(`/games/${gameId}/action`, {
        player_id: playerId,
        action: actionType,
        amount,
        use_ability_first: useAbilityFirst,
        ability_target_id: abilityTargetId,
      }),
    )
  }

  // POST /games/{game_id}/ability — fire a role ability outside betting
  // (between hands). During a betting turn the ability rides on /action via
  // use_ability_first instead; the engine rejects /ability mid-street.
  function ability({ playerId, abilityType, targetId = null }) {
    apply(() =>
      post(`/games/${gameId}/ability`, {
        player_id: playerId,
        ability_type: abilityType,
        target_id: targetId,
      }),
    )
  }

  // Auto-refresh: while a game is active, poll GET /games/{id} every ~2s and
  // store the result, so server-side changes show up without clicking Refresh.
  // Polling is a *side effect* (a timer + network I/O), so it lives in a
  // useEffect rather than in render. It stops when there is no game or the
  // game is over.
  const phase = gameState?.phase ?? null
  useEffect(() => {
    if (!gameId || phase === 'GAME_OVER') return // nothing to poll
    const timer = setInterval(() => {
      api(`/games/${gameId}`)
        .then((next) =>
          // Skip the update when the payload is identical: returning the SAME
          // reference makes React bail out of re-rendering (no churn every 2s).
          setGameState((prev) =>
            JSON.stringify(prev) === JSON.stringify(next) ? prev : next,
          ),
        )
        .catch(() => {}) // ignore a transient poll failure; the next tick retries
    }, POLL_MS)
    // Cleanup: clear THIS interval before the effect re-runs (gameId/phase
    // changed) or App unmounts — otherwise each run would stack another timer.
    return () => clearInterval(timer)
  }, [gameId, phase])

  // Derive per-seat last-action labels from state.events. The engine clears
  // events on each mutating call but re-sends the same batch on GET polls, so
  // we fingerprint the batch and only reprocess a genuinely new one.
  const lastEventsKey = useRef('')
  useEffect(() => {
    const events = gameState?.events ?? []
    const key = JSON.stringify(events)
    if (key === lastEventsKey.current) return // same batch → nothing new
    lastEventsKey.current = key
    setLastActions((prev) => applyEventLabels(prev, events))
  }, [gameState])

  // Load the cheat-hand options once — static reference data for the Shuffle
  // dropdown (lets the human dealer rig the deck instead of only shuffling honest).
  useEffect(() => {
    api('/cheat-hands').then(setCheatHands).catch(() => {})
  }, [])

  // Read the players and community cards out of the current state. Pure
  // reading — no fetch logic involved.
  const players = gameState?.players ?? []
  const communityCards = gameState?.community_cards ?? []
  // Side pots: shown only if the backend exposes them (it doesn't yet — the
  // state has only `pot` — so this is empty for now and renders nothing).
  const sidePots = gameState?.side_pots ?? []
  const activeId = activePlayerId(gameState) // whose turn it is (null = nobody)
  const log = gameState?.log ?? [] // backend's human-readable event feed
  const myId = players.find((p) => p.is_human)?.id ?? null

  // Curse highlight: the victim's id from this events batch (null = none), plus
  // a key that changes per batch so the pulse replays on each new curse.
  const curseTargetId =
    (gameState?.events ?? []).find((e) => e.type === 'cursed')?.target_id ?? null
  const curseKey = JSON.stringify(gameState?.events ?? [])

  // Phase + whose turn, as a status line.
  const actor = players.find((p) => p.id === activeId)
  const statusText = gameState
    ? gameState.phase.replaceAll('_', ' ') +
      (actor ? (actor.is_human ? ' — your turn' : ` — ${actor.name}'s turn`) : '')
    : 'No game yet'

  // The screen is just a description of these values. Any setter above
  // re-renders App and this redraws from the new state — no DOM poking.
  return (
    <div>
      <h1>♠ Texas Hold'em RPG ♠</h1>

      <div className="toolbar">
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          title="Pick your role before starting; bots draw random roles"
        >
          <option value="">no role</option>
          <option value="CURSED">CURSED</option>
          <option value="GUNNER">GUNNER</option>
          <option value="LUCKY">LUCKY</option>
        </select>
        <button className="primary" onClick={newGame}>
          New Game
        </button>
        <button onClick={refresh} disabled={!gameId}>
          Refresh
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {gameState && <p className="status">{statusText}</p>}

      {/* The accuse tell: how long the dealer "shuffled" (cheat mini-game). */}
      {gameState?.cheat_elapsed != null && (
        <p className="shuffle-time">
          ⏱ dealer shuffled for {gameState.cheat_elapsed.toFixed(1)} s
        </p>
      )}

      {/* Pre-game welcome card, in the spot where the felt will appear. */}
      {!gameState && (
        <div className="welcome">
          <p>
            <strong>Pull up a chair.</strong>
          </p>
          <p>
            Pick a role — or none — and hit New Game to sit down against three
            bots. Keep an eye on how long the dealer shuffles… the deck might
            be rigged.
          </p>
        </div>
      )}

      {players.length > 0 && (
        <div
          style={{
            position: 'relative',
            height: 430,
            maxWidth: 600,
            margin: '1.5rem auto 2.25rem',
            borderRadius: 170,
            background:
              'radial-gradient(ellipse at 50% 42%, #2f8757 0%, #257049 45%, #1a5639 75%, #123c28 100%)',
            border: '12px solid #53351d',
            boxShadow:
              '0 18px 40px rgba(0,0,0,0.5), inset 0 0 60px rgba(0,0,0,0.45)',
          }}
        >
          {/* Centre of the table: the community board (cards deal in with a
              stagger) and the pot / side-pots stacked just below it. */}
          <div
            style={{
              position: 'absolute',
              left: '50%',
              top: '50%',
              transform: 'translate(-50%, -50%)',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '0.6rem',
            }}
          >
            <div style={{ display: 'flex', gap: '0.35rem' }}>
              {Array.from({ length: 5 }, (_, i) => {
                const c = communityCards[i]
                return c ? (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, y: -18, scale: 0.85 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    transition={{ duration: 0.3, delay: i * 0.07 }}
                  >
                    <Card rank={c.rank} suit={c.suit} />
                  </motion.div>
                ) : (
                  <div key={i} className="card slot" />
                )
              })}
            </div>

            <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
              <span style={POT_PILL}>Pot: {gameState.pot}</span>
              {sidePots.map((sp, i) => (
                <span key={i} style={SIDE_POT_PILL}>
                  Side pot: {typeof sp === 'number' ? sp : sp.amount}
                </span>
              ))}
            </div>
          </div>

          {/* Seats layer: one <PlayerSeat> per player, placed on the ellipse.
              key={p.id} gives each seat a stable identity. dealerPos +
              hand_active_ids drive the dealer/blind markers; isActive lights
              up whoever is on the clock. */}
          <div style={{ position: 'absolute', inset: 0 }}>
            {players.map((p, i) => (
              <PlayerSeat
                key={p.id}
                player={p}
                index={i}
                total={players.length}
                dealerPos={gameState.dealer_pos}
                handActiveIds={gameState.hand_active_ids}
                isActive={p.id === activeId}
                lastAction={lastActions[p.id]}
                handResult={gameState.hand_result}
                phase={gameState.phase}
                isCursed={p.id === curseTargetId}
                curseKey={curseKey}
              />
            ))}
          </div>

          {/* "HAND OVER" banner — rendered only when the hand has ended. */}
          {gameState.phase === 'HAND_OVER' && (
            <div
              style={{
                position: 'absolute',
                left: '50%',
                top: '14%',
                transform: 'translateX(-50%)',
                padding: '0.4rem 1.5rem',
                fontSize: '1.3rem',
                fontWeight: 'bold',
                letterSpacing: '0.15em',
                color: '#e9c46a',
                background: 'rgba(0,0,0,0.6)',
                border: '1px solid rgba(233,196,106,0.6)',
                borderRadius: 8,
                boxShadow: '0 4px 14px rgba(0,0,0,0.6)',
              }}
            >
              HAND OVER
            </div>
          )}

          {/* Accusation/verdict drama, queued and centred over the felt. */}
          <AnnounceBanner state={gameState} />

          {/* Red flash when a shoot resolves (Framer Motion demo). */}
          <ShootFlash state={gameState} />
        </div>
      )}

      {/* In-game controls. App passes its endpoint functions down; ActionBar
          calls them from its buttons' onClick (events flow back up to App). */}
      <ActionBar
        state={gameState}
        activeId={activeId}
        startHand={startHand}
        shuffle={shuffle}
        accuse={accuse}
        action={action}
        ability={ability}
        cheatHands={cheatHands}
      />

      {/* Scrolling event feed from state.log (filtered to my visible lines). */}
      <EventLog log={log} myId={myId} />

      {/* Raw state, tucked away for debugging — same idea as /classic. */}
      {gameState && (
        <details className="debug">
          <summary>Raw state (debug)</summary>
          <p className="game-id">
            Game ID: <code>{gameId}</code>
          </p>
          <pre>{JSON.stringify(gameState, null, 2)}</pre>
        </details>
      )}
    </div>
  )
}

export default App
