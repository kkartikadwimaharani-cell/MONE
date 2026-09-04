(() => {
  const pet = document.getElementById('maintenancePet');
  const bubble = document.getElementById('maintenancePetBubble');
  const scene = document.getElementById('maintenanceScene');
  if (!pet || !bubble || !scene) return;

  const REACTIONS = [
    { state: 'disturbed', message: '...' },
    { state: 'disturbed', message: 'MMH.' },
    { state: 'annoyed', message: "I'M SLEEPING." },
    { state: 'bonk', message: 'STOP.' },
  ];
  const RESET_AFTER_MS = 4200;
  let tapCount = 0;
  let lastTapAt = 0;
  let resetTimer = 0;

  function setState(state, message = '') {
    pet.dataset.state = state;
    bubble.textContent = message;
  }

  function returnToSleep() {
    window.clearTimeout(resetTimer);
    resetTimer = 0;
    tapCount = 0;
    setState('sleep');
  }

  function scheduleSleep() {
    window.clearTimeout(resetTimer);
    resetTimer = window.setTimeout(returnToSleep, RESET_AFTER_MS);
  }

  function restartBonkAnimation() {
    pet.dataset.state = 'annoyed';
    void pet.offsetWidth;
    pet.dataset.state = 'bonk';
    scene.classList.remove('is-bonked');
    void scene.offsetWidth;
    scene.classList.add('is-bonked');
  }

  pet.addEventListener('click', () => {
    const now = Date.now();
    if (now - lastTapAt > RESET_AFTER_MS) tapCount = 0;
    lastTapAt = now;
    tapCount += 1;
    const reaction = REACTIONS[Math.min(tapCount - 1, REACTIONS.length - 1)];
    setState(reaction.state, tapCount > 4 ? 'I SAID, WAIT.' : reaction.message);
    if (reaction.state === 'bonk') restartBonkAnimation();
    scheduleSleep();
  });

  scene.addEventListener('animationend', (event) => {
    if (event.animationName === 'maintenanceScreenBonk') scene.classList.remove('is-bonked');
  });

  document.addEventListener('visibilitychange', () => {
    pet.classList.toggle('is-paused', document.hidden);
    scene.classList.toggle('is-paused', document.hidden);
    if (document.hidden) window.clearTimeout(resetTimer);
    else if (pet.dataset.state !== 'sleep') scheduleSleep();
  }, { passive: true });
})();
