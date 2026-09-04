export class PetStateMachine {
  constructor(states, initialState = 'idle') {
    if (!states[initialState]) throw new Error(`Unknown initial pet state: ${initialState}`);
    this.states = states;
    this.current = initialState;
    this.listeners = new Set();
  }

  get definition() {
    return this.states[this.current];
  }

  transition(nextState, detail = {}) {
    if (!this.states[nextState]) return false;
    if (nextState === this.current && !detail.restart) return false;
    const previous = this.current;
    this.current = nextState;
    this.listeners.forEach((listener) => listener({ previous, current: nextState, detail }));
    return true;
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}
