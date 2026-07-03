import { useState, useEffect, useRef } from 'react'
import './AnnounceBanner.css'

// Pull the dramatic accusation/verdict lines out of an events batch — the same
// messages (and CSS classes) the old processEvents() queued.
function extractAnnouncements(state) {
  const events = state?.events ?? []
  const players = state?.players ?? []
  const name = (id) => players.find((p) => p.id === id)?.name ?? id
  const out = []
  for (const ev of events) {
    switch (ev.type) {
      case 'human_accused':
      case 'bot_accused':
        out.push({ text: `${name(ev.accuser_id)} accuses the dealer!`, cls: 'suspense', ms: 1500 })
        break
      case 'caught_cheating':
        out.push({
          text: `CAUGHT! ${name(ev.dealer_id)} rigged the deck — pays ${ev.penalty}, redeal`,
          cls: 'caught',
          ms: 3000,
        })
        break
      case 'false_accusation':
        out.push({
          text: `Honest shuffle — ${name(ev.accuser_id)}'s accusation costs ${2 * state.big_blind}`,
          cls: 'honest',
          ms: 3000,
        })
        break
      case 'lucky_escape':
        out.push({
          text: `${name(ev.dealer_id)} slips the accusation… a lucky escape!`,
          cls: 'escape',
          ms: 3000,
        })
        break
      default:
        break
    }
  }
  return out
}

// Banner over the felt that plays accusation drama in sequence. Each new events
// batch appends to a queue; queue[0] shows until its (cumulative) expiry, then a
// steady tick drops it and the next plays.
function AnnounceBanner({ state }) {
  const [queue, setQueue] = useState([])
  const seenKey = useRef('')
  const lastExpiry = useRef(0)

  // Enqueue from each genuinely new events batch (polls re-send the same one,
  // so fingerprint and skip). Expiry timestamps are computed here, not inside
  // the updater, so the state change stays a plain append; each item stacks
  // after the previous so they play back-to-back.
  useEffect(() => {
    const key = JSON.stringify(state?.events ?? [])
    if (key === seenKey.current) return
    seenKey.current = key
    const anns = extractAnnouncements(state)
    if (!anns.length) return
    let t = Math.max(Date.now(), lastExpiry.current)
    const stamped = anns.map((a) => {
      t += a.ms
      return { ...a, expiresAt: t }
    })
    lastExpiry.current = t
    setQueue((q) => [...q, ...stamped])
  }, [state])

  // Steady tick drops expired items (front first). Deps [] — it never depends
  // on `queue`, so it isn't a self-updating effect. setState bails out (same
  // reference) when nothing expired, so an idle tick costs no re-render.
  useEffect(() => {
    const id = setInterval(() => {
      const now = Date.now()
      setQueue((q) => (q.length && q[0].expiresAt <= now ? q.slice(1) : q))
    }, 250)
    return () => clearInterval(id)
  }, [])

  const showing = queue[0]
  if (!showing) return null
  return <div className={`announce ${showing.cls}`}>{showing.text}</div>
}

export default AnnounceBanner
