function rectsOverlap(a, b, padding) {
  return !(
    a.right + padding < b.left ||
    a.left - padding > b.right ||
    a.bottom + padding < b.top ||
    a.top - padding > b.bottom
  );
}

function isVisible(element) {
  const style = window.getComputedStyle(element);
  if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.top < window.innerHeight;
}

export class WaypointManager {
  constructor(root, config) {
    this.root = root;
    this.config = config;
    this.current = { x: 18, y: 18 };
    this.safeWaypoints = [];
  }

  petSize() {
    const rect = this.root.getBoundingClientRect();
    return { width: rect.width || 112, height: rect.height || 122 };
  }

  blockedRects() {
    const selector = this.config.importantSelectors.join(',');
    return Array.from(document.querySelectorAll(selector))
      .filter((element) => !this.root.contains(element) && isVisible(element))
      .map((element) => element.getBoundingClientRect());
  }

  refresh() {
    const { width, height } = this.petSize();
    const movement = this.config.movement;
    const maxX = Math.max(movement.viewportPadding, window.innerWidth - width - movement.viewportPadding);
    const maxY = Math.max(movement.viewportPadding, window.innerHeight - height - movement.viewportPadding);
    const blocked = this.blockedRects();
    const candidates = [];

    for (let row = 0; row < movement.candidateRows; row += 1) {
      const y = movement.viewportPadding + (maxY - movement.viewportPadding) * (row / Math.max(1, movement.candidateRows - 1));
      for (let column = 0; column < movement.candidateColumns; column += 1) {
        const x = movement.viewportPadding + (maxX - movement.viewportPadding) * (column / Math.max(1, movement.candidateColumns - 1));
        const candidate = { left: x, top: y, right: x + width, bottom: y + height };
        if (!blocked.some((rect) => rectsOverlap(candidate, rect, movement.collisionPadding))) {
          candidates.push({ x: Math.round(x), y: Math.round(y) });
        }
      }
    }

    this.safeWaypoints = candidates.length ? candidates : [
      { x: movement.viewportPadding, y: maxY },
      { x: maxX, y: maxY }
    ];
    return this.safeWaypoints;
  }

  nearestSafe(point = this.current) {
    const points = this.safeWaypoints.length ? this.safeWaypoints : this.refresh();
    return points.reduce((best, candidate) => {
      const distance = Math.hypot(candidate.x - point.x, candidate.y - point.y);
      return !best || distance < best.distance ? { ...candidate, distance } : best;
    }, null);
  }

  randomSafe({ awayFrom = this.current, minDistance = 80 } = {}) {
    const points = this.refresh();
    const sameLane = points.filter((point) => Math.abs(point.y - awayFrom.y) <= 42);
    const naturalPool = sameLane.length >= 2 ? sameLane : points;
    const distant = naturalPool.filter((point) => Math.hypot(point.x - awayFrom.x, point.y - awayFrom.y) >= minDistance);
    const pool = distant.length ? distant : naturalPool;
    return pool[Math.floor(Math.random() * pool.length)];
  }

  besideInteractiveElement() {
    const selector = this.config.importantSelectors.join(',');
    const elements = Array.from(document.querySelectorAll(selector)).filter((element) => {
      if (this.root.contains(element) || !isVisible(element)) return false;
      const rect = element.getBoundingClientRect();
      return rect.width >= 52 && rect.height >= 30 && rect.width < window.innerWidth * 0.9;
    });
    if (!elements.length) return null;

    const target = elements[Math.floor(Math.random() * elements.length)].getBoundingClientRect();
    const { width, height } = this.petSize();
    const preferred = [
      { x: target.left - width - 16, y: target.bottom - height },
      { x: target.right + 16, y: target.bottom - height }
    ];
    const points = this.refresh();
    return points.reduce((best, point) => {
      const distance = Math.min(...preferred.map((candidate) => Math.hypot(candidate.x - point.x, candidate.y - point.y)));
      return !best || distance < best.distance ? { ...point, distance } : best;
    }, null);
  }

  apply(point) {
    this.current = { x: Math.round(point.x), y: Math.round(point.y) };
    this.root.style.setProperty('--pet-x', `${this.current.x}px`);
    this.root.style.setProperty('--pet-y', `${this.current.y}px`);
  }
}
