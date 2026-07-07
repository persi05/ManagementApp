(() => {
  const timerRoot = document.querySelector('[data-timer-root]');
  if (!timerRoot || !timerRoot.dataset.startedAt) return;

  const readout = timerRoot.querySelector('[data-timer-readout]');
  const startedAt = new Date(timerRoot.dataset.startedAt).getTime();
  const pausedAt = timerRoot.dataset.pausedAt ? new Date(timerRoot.dataset.pausedAt).getTime() : null;
  const isRunning = timerRoot.dataset.state === 'running';
  const isPaused = timerRoot.dataset.state === 'paused';
  const inactiveFields = document.querySelectorAll('[data-inactive-field]');
  const savedInactiveMinutes = Number(timerRoot.dataset.inactiveMinutes || 0);
  let newInactiveMinutes = 0;
  let lastActivity = Date.now();
  let warned = false;
  let modalShown = false;

  const format = (seconds) => {
    const h = String(Math.floor(seconds / 3600)).padStart(2, '0');
    const m = String(Math.floor((seconds % 3600) / 60)).padStart(2, '0');
    const s = String(seconds % 60).padStart(2, '0');
    return `${h}:${m}:${s}`;
  };

  const setInactive = () => inactiveFields.forEach((field) => {
    field.value = newInactiveMinutes;
  });

  const markActive = () => {
    lastActivity = Date.now();
    warned = false;
    document.querySelector('.idle-toast')?.remove();
  };

  ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'].forEach((eventName) => {
    window.addEventListener(eventName, markActive, { passive: true });
  });

  const showToast = () => {
    if (document.querySelector('.idle-toast')) return;
    const toast = document.createElement('div');
    toast.className = 'idle-toast';
    toast.textContent = 'Brak aktywności. Za chwilę licznik zostanie oznaczony jako nieaktywny.';
    document.body.appendChild(toast);
  };

  const showModal = () => {
    if (modalShown) return;
    modalShown = true;
    const modal = document.createElement('div');
    modal.className = 'idle-modal';
    modal.innerHTML = '<div><h2>Czy nadal pracujesz?</h2><p>Potwierdź aktywność, aby licznik działał dalej bez doliczania czasu nieaktywnego.</p><button class="primary-btn full" type="button">Pracuję dalej</button></div>';
    modal.querySelector('button').addEventListener('click', () => {
      modal.remove();
      modalShown = false;
      markActive();
    });
    document.body.appendChild(modal);
  };

  setInterval(() => {
    if (readout) {
      const endAt = isPaused && pausedAt ? pausedAt : Date.now();
      const elapsed = Math.max(0, Math.floor((endAt - startedAt) / 1000) - (savedInactiveMinutes + newInactiveMinutes) * 60);
      readout.textContent = format(elapsed);
    }

    if (!isRunning) return;

    const idleMs = Date.now() - lastActivity;
    if (idleMs > 30 * 60 * 1000 && !warned) {
      warned = true;
      showToast();
    }

    if (idleMs > 35 * 60 * 1000) {
      newInactiveMinutes += 5;
      setInactive();
      showModal();
      lastActivity = Date.now();
    }
  }, 1000);
})();
