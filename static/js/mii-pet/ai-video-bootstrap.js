import { AiVideoPetController } from './ai-video-controller.js';

const root = document.createElement('div');
root.className = 'mii-work-pet';
root.setAttribute('aria-hidden', 'true');
root.innerHTML = '<div class="mii-work-pet__status"></div><div class="mii-work-pet__sprite"></div>';
const canvas = document.getElementById('pageAiVideo') || document.querySelector('.canvas');
(canvas || document.body).appendChild(root);

const controller = new AiVideoPetController(root);
controller.start();
window.addEventListener('pagehide', () => controller.destroy(), { once: true });
