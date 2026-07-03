import { motion } from 'motion/react'

// Events that mean "a trigger was pulled" — opponent shots (hit/miss) and the
// self / bust-revival roulette (bang = died, click = survived).
const SHOOT_EVENTS = ['shot_hit', 'shot_miss', 'revolver_bang', 'revolver_click']

// A brief red flash over the felt whenever a shoot resolves. No state, no
// effect: it's derived straight from state.events during render. Framer Motion
// does the animation declaratively, and the `key` (the events fingerprint)
// changes on each new shoot batch, which remounts the element so the flash
// replays. This is the pattern — describe the animated element, let Motion run it.
function ShootFlash({ state }) {
  const events = state?.events ?? []
  if (!events.some((e) => SHOOT_EVENTS.includes(e.type))) return null

  return (
    <motion.div
      key={JSON.stringify(events)} // new shoot batch → new key → replay
      initial={{ opacity: 0 }}
      animate={{ opacity: [0, 0.6, 0] }} // fade in, then back out (ends invisible)
      transition={{ duration: 0.6, times: [0, 0.25, 1] }}
      style={{
        position: 'absolute',
        inset: 0,
        borderRadius: 140,
        background:
          'radial-gradient(circle, rgba(255,60,60,0.85), rgba(255,0,0,0.15))',
        pointerEvents: 'none', // never blocks clicks on the table
        zIndex: 4,
      }}
    />
  )
}

export default ShootFlash
