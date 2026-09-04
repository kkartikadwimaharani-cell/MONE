import { PetStateMachine } from './state-machine.js';
import { AI_VIDEO_COPY, AI_VIDEO_STATES } from './ai-video-config.js';

const EVENT_NAME = 'mii-pet:generation';

export class AiVideoPetController {
  constructor(root) {
    this.root = root;
    this.sprite = root.querySelector('.mii-work-pet__sprite');
    this.status = root.querySelector('.mii-work-pet__status');
    this.machine = new PetStateMachine(AI_VIDEO_STATES, 'idle');
    this.frame = 0;
    this.frameTimer = 0;
    this.behaviorTimer = 0;
    this.statusTimer = 0;
    this.activeTasks = new Map();
    this.paused = document.hidden;
    this.onGeneration = this.onGeneration.bind(this);
    this.onVisibility = this.onVisibility.bind(this);
    this.onPointer = this.onPointer.bind(this);
  }

  start() {
    this.unsubscribe = this.machine.subscribe(() => this.renderState());
    window.addEventListener(EVENT_NAME, this.onGeneration);
    document.addEventListener('visibilitychange', this.onVisibility);
    document.addEventListener('pointerdown', this.onPointer, { passive: true });
    this.renderState();
    this.scheduleIdleBehavior();
  }

  destroy() {
    window.removeEventListener(EVENT_NAME, this.onGeneration);
    document.removeEventListener('visibilitychange', this.onVisibility);
    document.removeEventListener('pointerdown', this.onPointer);
    clearTimeout(this.frameTimer);
    clearTimeout(this.behaviorTimer);
    clearTimeout(this.statusTimer);
    this.unsubscribe?.();
  }

  onGeneration(event) {
    const detail = event.detail || {};
    const taskId = detail.taskId || 'submitting';
    const status = String(detail.status || 'processing').toLowerCase();

    const previousStatus = this.activeTasks.get(taskId);
    if (status !== 'submitting') this.activeTasks.delete('submitting');
    if (status === 'completed' || status === 'failed') this.activeTasks.delete(taskId);
    else this.activeTasks.set(taskId, status);

    const state = status === 'completed' ? 'review'
      : status === 'failed' ? 'failed'
      : status === 'pending' || status === 'submitting' ? 'waiting'
      : 'working';
    this.machine.transition(state, { restart: state === 'review' || state === 'failed' });
    if (previousStatus !== status || status === 'completed' || status === 'failed') {
      this.showStatus(AI_VIDEO_COPY[status] || AI_VIDEO_COPY.processing);
    }

    if (status === 'completed' || status === 'failed') {
      clearTimeout(this.behaviorTimer);
      this.behaviorTimer = window.setTimeout(() => this.syncTaskState(), 2600);
    }
  }

  syncTaskState() {
    if (this.activeTasks.size) this.machine.transition('working');
    else {
      this.machine.transition('idle');
      this.scheduleIdleBehavior();
    }
  }

  onPointer(event) {
    if (this.paused) return;
    const rect = this.root.getBoundingClientRect();
    const insetX = rect.width * .27;
    const insetTop = rect.height * .12;
    if (event.clientX < rect.left + insetX || event.clientX > rect.right - insetX) return;
    if (event.clientY < rect.top + insetTop || event.clientY > rect.bottom) return;
    this.machine.transition('reacting', { restart: true });
    this.showStatus(AI_VIDEO_COPY.reacting);
    clearTimeout(this.behaviorTimer);
    this.behaviorTimer = window.setTimeout(() => this.syncTaskState(), 1500);
  }

  onVisibility() {
    this.paused = document.hidden;
    this.root.classList.toggle('is-paused', this.paused);
    clearTimeout(this.frameTimer);
    clearTimeout(this.behaviorTimer);
    if (!this.paused) {
      this.renderState();
      this.scheduleIdleBehavior();
    }
  }

  renderState() {
    clearTimeout(this.frameTimer);
    if (this.paused) return;
    this.frame = 0;
    this.renderFrame();
  }

  renderFrame() {
    if (this.paused) return;
    const state = this.machine.definition;
    const x = (this.frame / 7) * 100;
    const y = (state.row / 4) * 100;
    this.sprite.style.backgroundPosition = `${x}% ${y}%`;
    this.frame += 1;
    if (this.frame >= state.frames) {
      if (state.once) return;
      this.frame = 0;
    }
    this.frameTimer = window.setTimeout(() => this.renderFrame(), 1000 / state.fps);
  }

  scheduleIdleBehavior() {
    clearTimeout(this.behaviorTimer);
    if (this.paused || this.activeTasks.size) return;
    const delay = 5200 + Math.random() * 5200;
    this.behaviorTimer = window.setTimeout(() => {
      this.machine.transition(this.machine.current === 'waiting' ? 'idle' : 'waiting');
      this.scheduleIdleBehavior();
    }, delay);
  }

  showStatus(message) {
    clearTimeout(this.statusTimer);
    this.status.textContent = message;
    this.status.classList.add('is-visible');
    this.statusTimer = window.setTimeout(() => this.status.classList.remove('is-visible'), 2200);
  }
}
