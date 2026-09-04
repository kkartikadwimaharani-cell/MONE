import { MiiPetEngine } from './engine.js';

function boot() {
  if (window.__miiPetEngine) return;
  const engine = new MiiPetEngine();
  window.__miiPetEngine = engine;
  engine.init().catch((error) => {
    console.warn('[MII Pet] Home pet failed to initialize.', error);
  });
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
else boot();
