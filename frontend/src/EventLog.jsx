import { useEffect, useRef } from 'react'
import './EventLog.css'

// Class for one log line: a private line (mine only) gets the gold + lock
// style; a "— Hand/Flop —" marker reads as a quiet divider; anything else is
// a plain public line. Same buckets as the old renderLog().
function lineClass(e) {
  if (e.private_to !== null) return 'log-private'
  if (e.text.startsWith('—')) return 'log-sep'
  return ''
}

// Scrolling feed of the backend's state.log. `log` is [{ text, private_to }];
// `myId` is the viewing human's id. Public lines plus my own private lines are
// shown; other players' secrets are filtered out. Newest line at the bottom,
// auto-scrolled into view as new lines arrive.
function EventLog({ log, myId }) {
  // useRef holds a handle to the scrollable <ol> DOM node. It persists across
  // renders and — unlike useState — changing it does NOT trigger a re-render,
  // which is exactly what we want for an imperative thing like scroll position.
  const listRef = useRef(null)

  // Show public lines (private_to === null) plus my own private lines.
  const visible = (log ?? []).filter(
    (e) => e.private_to === null || e.private_to === myId,
  )

  // After React has rendered the new lines to the DOM, pin the scroll to the
  // bottom so the newest entry is visible. useEffect runs after paint, so
  // scrollHeight already reflects the added lines. Re-runs only when the
  // number of visible lines changes (new lines arrived, or the log reset
  // between hands) — so an unchanged render won't fight a user scrolling up.
  useEffect(() => {
    const el = listRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [visible.length])

  return (
    <div className="log-panel">
      <div className="log-header">Game Log</div>
      {/* ref={listRef} wires this <ol> to the ref above. */}
      <ol className="log-list" ref={listRef}>
        {visible.length === 0 ? (
          <li className="log-empty">No events yet.</li>
        ) : (
          visible.map((e, i) => (
            <li key={i} className={lineClass(e)}>
              {e.text}
            </li>
          ))
        )}
      </ol>
    </div>
  )
}

export default EventLog
