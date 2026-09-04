import { PET_CONFIG, randomBetween } from './config.js';
import { PetStateMachine } from './state-machine.js';
import { WaypointManager } from './waypoints.js';
import { HomeBehavior } from './home-behavior.js';

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function throttle(callback, delay) {
  let pending = false;
  return () => {
    if (pending) return;
    pending = true;
    window.setTimeout(() => {
      pending = false;
      callback();
    }, delay);
  };
}

export class MiiPetEngine {
  constructor(config = PET_CONFIG) {
    this.config = config;
    this.machine = new PetStateMachine(config.states);
    this.frame = 0;
    this.frameTimer = 0;
    this.onceResolver = null;
    this.active = false;
    this.lastInteraction = 0;
    this.transitioning = false;
    this.root = this.createRoot();
    this.sprite = this.root.querySelector('.mii-pet__sprite');
    this.waypoints = new WaypointManager(this.root, config);
    this.behavior = new HomeBehavior(this, config);
    this.unsubscribe = this.machine.subscribe(() => this.onStateChanged());
    this.onViewportChange = throttle(() => this.reconcilePosition(), 140);
    this.onDocumentPointer = (event) => this.handlePointer(event);
    this.onVisibilityChange = () => this.syncActivity();
    this.onRouteSignal = () => window.setTimeout(() => this.syncActivity(), 0);
    this.onNavigationClick = (event) => this.handleNavigationClick(event);
  }

  createRoot() {
    const root = document.createElement('div');
    root.className = 'mii-pet mii-pet--hidden';
    root.setAttribute('aria-hidden', 'true');
    root.innerHTML = '<div class="mii-pet__shadow"></div><div class="mii-pet__sprite"></div><div class="mii-pet__hint">tap!</div>';
    document.body.appendChild(root);
    return root;
  }

  async init() {
    await this.preloadSprite();
    this.bind();
    this.waypoints.refresh();
    const initial = this.waypoints.lowestSafe();
    this.waypoints.apply(initial);
    this.syncActivity(true);
  }

  preloadSprite() {
    return new Promise((resolve) => {
      const image = new Image();
      image.decoding = 'async';
      image.onload = () => resolve(true);
      image.onerror = () => resolve(false);
      image.src = this.config.spriteUrl;
    }).then((loaded) => {
      if (!loaded) this.root.classList.add('mii-pet--asset-error');
      else this.sprite.style.backgroundImage = `url("${this.config.spriteUrl}")`;
      return loaded;
    });
  }

  bind() {
    document.addEventListener('pointerdown', this.onDocumentPointer, { passive: true });
    document.addEventListener('click', this.onRouteSignal, { passive: true });
    document.addEventListener('click', this.onNavigationClick);
    document.addEventListener('visibilitychange', this.onVisibilityChange);
    window.addEventListener('resize', this.onViewportChange, { passive: true });
    window.addEventListener('scroll', this.onViewportChange, { passive: true });
    window.addEventListener('popstate', this.onRouteSignal);
  }

  isHomeVisible() {
    const home = document.getElementById('viewDownloader');
    if (!home) return false;
    return window.getComputedStyle(home).display !== 'none';
  }

  syncActivity(firstRun = false) {
    const shouldRun = !document.hidden && this.isHomeVisible();
    if (shouldRun === this.active) return;
    this.active = shouldRun;
    this.root.classList.toggle('mii-pet--hidden', !shouldRun);
    if (shouldRun) {
      this.reconcilePosition();
      this.startFrameLoop();
      this.behavior.start(firstRun);
    } else {
      this.behavior.stop();
      this.stopFrameLoop();
    }
  }

  setState(state, detail = {}) {
    this.machine.transition(state, detail);
  }

  onStateChanged() {
    this.frame = 0;
    this.root.dataset.state = this.machine.current;
    this.renderFrame();
  }

  startFrameLoop() {
    this.stopFrameLoop();
    const tick = () => {
      if (!this.active || document.hidden) return;
      const definition = this.machine.definition;
      this.frame += 1;
      if (this.frame >= definition.frames) {
        if (definition.loop) this.frame = 0;
        else {
          this.frame = definition.frames - 1;
          const resolve = this.onceResolver;
          this.onceResolver = null;
          if (resolve) resolve();
        }
      }
      this.renderFrame();
      this.frameTimer = window.setTimeout(tick, Math.round(1000 / definition.fps));
    };
    this.renderFrame();
    this.frameTimer = window.setTimeout(tick, Math.round(1000 / this.machine.definition.fps));
  }

  stopFrameLoop() {
    window.clearTimeout(this.frameTimer);
    this.frameTimer = 0;
  }

  renderFrame() {
    const definition = this.machine.definition;
    const width = this.sprite.clientWidth || 112;
    const height = this.sprite.clientHeight || Math.round(width * this.config.sheet.cellHeight / this.config.sheet.cellWidth);
    this.sprite.style.backgroundSize = `${width * this.config.sheet.columns}px ${height * this.config.sheet.rows}px`;
    this.sprite.style.backgroundPosition = `${-this.frame * width}px ${-definition.row * height}px`;
  }

  async performOnce(state) {
    if (!this.active) return;
    if (this.onceResolver) this.onceResolver();
    this.setState(state, { restart: true });
    this.startFrameLoop();
    await new Promise((resolve) => { this.onceResolver = resolve; });
  }

  async walkTo(point) {
    if (!point || !this.active) return;
    const from = this.waypoints.current;
    const distance = Math.hypot(point.x - from.x, point.y - from.y);
    if (distance < 12) return;
    const movingRight = point.x >= from.x;
    this.setState(movingRight ? 'walkingRight' : 'walkingLeft');
    this.startFrameLoop();
    const speed = window.matchMedia('(max-width: 640px)').matches
      ? this.config.movement.speedMobile : this.config.movement.speedDesktop;
    const duration = Math.min(this.config.movement.maxTravelSeconds,
      Math.max(this.config.movement.minTravelSeconds, distance / speed));
    this.root.style.setProperty('--pet-move-duration', `${duration.toFixed(2)}s`);
    this.root.classList.add('mii-pet--moving');
    this.waypoints.apply(point);
    await wait(duration * 1000);
    this.root.classList.remove('mii-pet--moving');
  }

  walkToRandomWaypoint() {
    return this.walkTo(this.waypoints.randomSafe({ minDistance: 88 }));
  }

  async rest() {
    this.setState('resting');
    this.startFrameLoop();
    await wait(randomBetween(this.config.timing.restMin, this.config.timing.restMax));
  }

  async inspectNearbyUI() {
    const point = this.waypoints.besideInteractiveElement();
    if (!point) return this.performOnce('curious');
    await this.walkTo(point);
    if (!this.active) return;
    this.root.classList.add('mii-pet--fake-tap');
    await this.performOnce('curious');
    this.root.classList.remove('mii-pet--fake-tap');
  }

  reconcilePosition() {
    if (!this.active) return;
    this.waypoints.refresh();
    const safe = this.waypoints.nearestSafe();
    if (!safe) return;
    const distance = Math.hypot(safe.x - this.waypoints.current.x, safe.y - this.waypoints.current.y);
    if (distance > 36) {
      this.root.style.setProperty('--pet-move-duration', '.3s');
      this.waypoints.apply(safe);
    }
    this.renderFrame();
  }

  handlePointer(event) {
    if (!this.active) return;
    const rect = this.sprite.getBoundingClientRect();
    const normalizedX = (event.clientX - rect.left) / rect.width;
    const normalizedY = (event.clientY - rect.top) / rect.height;
    const insideBody = normalizedX > 0.22 && normalizedX < 0.78 && normalizedY > 0.04 && normalizedY < 0.98;
    if (!insideBody || Date.now() - this.lastInteraction < this.config.timing.interactionCooldown) return;
    this.lastInteraction = Date.now();
    this.root.classList.add('mii-pet--touched');
    window.setTimeout(() => this.root.classList.remove('mii-pet--touched'), 420);
    this.behavior.nudge();
  }

  handleNavigationClick(event) {
    if (!this.active || this.transitioning || event.defaultPrevented || event.button !== 0) return;
    if (this.root.classList.contains('mii-pet--asset-error')) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest?.('a[href]');
    if (!link || link.target === '_blank' || link.hasAttribute('download')) return;
    const target = new URL(link.href, window.location.href);
    if (target.origin !== window.location.origin || target.pathname !== '/ai-video') return;
    event.preventDefault();
    this.exitTo(target.href);
  }

  async exitTo(url) {
    if (this.transitioning) return;
    this.transitioning = true;
    this.behavior.stop();
    const rect = this.root.getBoundingClientRect();
    const leaveRight = rect.left + rect.width / 2 >= window.innerWidth / 2;
    const destinationX = leaveRight ? window.innerWidth + rect.width + 20 : -rect.width - 20;
    const distance = leaveRight ? destinationX - rect.left : rect.left - destinationX;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const duration = reducedMotion ? .05 : Math.min(1.1, Math.max(.45, distance / 520));

    this.setState(leaveRight ? 'walkingRight' : 'walkingLeft');
    this.startFrameLoop();
    this.root.style.setProperty('--pet-move-duration', `${duration.toFixed(2)}s`);
    this.root.style.setProperty('--pet-x', `${destinationX}px`);
    try {
      sessionStorage.setItem('mii-pet-page-transition', JSON.stringify({
        from: 'home', side: leaveRight ? 'right' : 'left', at: Date.now()
      }));
    } catch (_) {}
    await wait(duration * 1000);
    window.location.assign(url);
  }
}
