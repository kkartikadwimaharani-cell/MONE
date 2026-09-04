import { AiVideoPetController } from './ai-video-controller.js';

const root = document.createElement('div');
root.className = 'mii-work-pet';
root.setAttribute('aria-hidden', 'true');
root.innerHTML = '<div class="mii-work-pet__status"></div><div class="mii-work-pet__sprite"></div>';
const canvas = document.getElementById('pageAiVideo') || document.querySelector('.canvas');
(canvas || document.body).appendChild(root);

try {
  const transition = JSON.parse(sessionStorage.getItem('mii-pet-page-transition') || 'null');
  sessionStorage.removeItem('mii-pet-page-transition');
  if (transition?.from === 'home' && Date.now() - transition.at < 8000) {
    const distance = transition.side === 'right'
      ? Math.max((canvas?.clientWidth || window.innerWidth) - root.offsetLeft + 24, root.offsetWidth + 24)
      : -(root.offsetLeft + root.offsetWidth + 24);
    root.style.setProperty('--mii-pet-entry-x', `${distance}px`);
    root.classList.add('mii-work-pet--entering');
    requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove('mii-work-pet--entering')));
  }
} catch (_) {}

const controller = new AiVideoPetController(root);
controller.start();
window.addEventListener('pagehide', () => controller.destroy(), { once: true });
