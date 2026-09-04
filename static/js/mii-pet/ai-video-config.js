export const AI_VIDEO_STATES = Object.freeze({
  idle: { row: 0, frames: 6, fps: 4 },
  waiting: { row: 1, frames: 6, fps: 3 },
  working: { row: 2, frames: 6, fps: 7 },
  review: { row: 3, frames: 6, fps: 5, once: true },
  failed: { row: 4, frames: 8, fps: 6, once: true },
  reacting: { row: 3, frames: 6, fps: 7, once: true },
});

export const AI_VIDEO_COPY = Object.freeze({
  submitting: 'Aku siapkan dulu…',
  pending: 'Menunggu giliran…',
  processing: 'Makima sedang mengawasi',
  saving: 'Merapikan hasil…',
  completed: 'Sudah selesai!',
  failed: 'Yah, coba lagi ya',
  reacting: 'Hm?',
});
