import { randomBetween } from './config.js';

export class HomeBehavior {
  constructor(engine, config) {
    this.engine = engine;
    this.config = config;
    this.timer = 0;
    this.running = false;
  }

  start(firstRun = false) {
    if (this.running) return;
    this.running = true;
    this.engine.setState('idle');
    this.schedule(firstRun ? this.config.timing.firstActionMin : this.config.timing.actionMin,
      firstRun ? this.config.timing.firstActionMax : this.config.timing.actionMax);
  }

  stop() {
    this.running = false;
    window.clearTimeout(this.timer);
    this.timer = 0;
  }

  schedule(min, max) {
    window.clearTimeout(this.timer);
    if (!this.running) return;
    this.timer = window.setTimeout(() => this.performRandomAction(), randomBetween(min, max));
  }

  async performRandomAction() {
    if (!this.running || document.hidden || !this.engine.isHomeVisible()) return;
    const roll = Math.random();
    if (roll < 0.5) await this.engine.walkToRandomWaypoint();
    else if (roll < 0.68) await this.engine.rest();
    else if (roll < 0.82) await this.engine.performOnce('waving');
    else if (roll < 0.93) await this.engine.inspectNearbyUI();
    else await this.engine.performOnce('jumping');

    if (!this.running) return;
    this.engine.setState('idle');
    this.schedule(this.config.timing.actionMin, this.config.timing.actionMax);
  }

  nudge() {
    if (!this.running) return;
    window.clearTimeout(this.timer);
    this.engine.performOnce(Math.random() > 0.45 ? 'waving' : 'reacting').finally(() => {
      if (!this.running) return;
      this.engine.setState('idle');
      this.schedule(this.config.timing.actionMin, this.config.timing.actionMax);
    });
  }
}
