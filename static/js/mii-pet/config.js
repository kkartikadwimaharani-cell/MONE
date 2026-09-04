export const PET_CONFIG = Object.freeze({
  name: 'Chibi Makima',
  page: 'home',
  spriteUrl: new URL('../../pet/chibi-makima/home-spritesheet.png', import.meta.url).href,
  sheet: Object.freeze({ columns: 8, rows: 9, cellWidth: 192, cellHeight: 208 }),
  states: Object.freeze({
    idle: Object.freeze({ row: 0, frames: 6, fps: 6, loop: true }),
    walkingRight: Object.freeze({ row: 1, frames: 8, fps: 12, loop: true }),
    walkingLeft: Object.freeze({ row: 2, frames: 8, fps: 12, loop: true }),
    waving: Object.freeze({ row: 3, frames: 4, fps: 7, loop: false }),
    jumping: Object.freeze({ row: 4, frames: 5, fps: 9, loop: false }),
    reacting: Object.freeze({ row: 5, frames: 8, fps: 9, loop: false }),
    resting: Object.freeze({ row: 6, frames: 6, fps: 5, loop: true }),
    curious: Object.freeze({ row: 8, frames: 6, fps: 6, loop: false })
  }),
  timing: Object.freeze({
    firstActionMin: 1800,
    firstActionMax: 3600,
    actionMin: 2400,
    actionMax: 6200,
    restMin: 1700,
    restMax: 3900,
    interactionCooldown: 650
  }),
  movement: Object.freeze({
    speedDesktop: 72,
    speedMobile: 58,
    minTravelSeconds: 0.8,
    maxTravelSeconds: 5.5,
    viewportPadding: 14,
    collisionPadding: 12,
    candidateColumns: 7,
    candidateRows: 4
  }),
  importantSelectors: Object.freeze([
    '.top-nav', '.side-drawer', '.hero-actions', '.premium-btn',
    '.social-card', '.project-card', 'button', 'a', 'input',
    'textarea', 'select', '[role="button"]'
  ])
});

export function randomBetween(min, max) {
  return Math.round(min + Math.random() * (max - min));
}
