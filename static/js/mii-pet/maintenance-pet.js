const pet = document.querySelector('.maintenance-sleep-pet');

if (pet) {
  const syncVisibility = () => pet.classList.toggle('is-paused', document.hidden);
  document.addEventListener('visibilitychange', syncVisibility, { passive: true });
  syncVisibility();
}
