(() => {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content
    || document.cookie.split('; ').find((row) => row.startsWith('csrftoken='))?.split('=')[1]
    || '';

  document.querySelectorAll('.kanban-card').forEach((card) => {
    card.addEventListener('dragstart', (event) => {
      card.classList.add('dragging');
      event.dataTransfer.setData('text/plain', card.dataset.task);
    });
    card.addEventListener('dragend', () => card.classList.remove('dragging'));
  });

  document.querySelectorAll('.kanban-column').forEach((column) => {
    column.addEventListener('dragover', (event) => event.preventDefault());
    column.addEventListener('drop', async (event) => {
      event.preventDefault();
      const card = document.querySelector(`.kanban-card[data-task="${event.dataTransfer.getData('text/plain')}"]`);
      if (!card) return;
      const previousDropzone = card.parentElement;
      const dropzone = column.querySelector('.kanban-dropzone');
      dropzone.appendChild(card);
      const body = new URLSearchParams({ column: column.dataset.column });
      const response = await fetch(card.dataset.moveUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrf, 'Content-Type': 'application/x-www-form-urlencoded' },
        credentials: 'same-origin',
        body,
      });
      if (!response.ok) {
        previousDropzone?.appendChild(card);
      }
    });
  });

  const timerRoot = document.querySelector('[data-timer-root]');
  if (!timerRoot || !timerRoot.dataset.startedAt) return;

  const readout = timerRoot.querySelector('[data-timer-readout]');
  const startedAt = new Date(timerRoot.dataset.startedAt).getTime();
  const isRunning = timerRoot.dataset.state === 'running';
  const inactiveFields = document.querySelectorAll('[data-inactive-field]');
  let inactiveMinutes = 0;
  let lastActivity = Date.now();
  let warned = false;
  let modalShown = false;

  const format = (seconds) => {
    const h = String(Math.floor(seconds / 3600)).padStart(2, '0');
    const m = String(Math.floor((seconds % 3600) / 60)).padStart(2, '0');
    const s = String(seconds % 60).padStart(2, '0');
    return `${h}:${m}:${s}`;
  };

  const setInactive = () => inactiveFields.forEach((field) => { field.value = inactiveMinutes; });
  const markActive = () => {
    lastActivity = Date.now();
    warned = false;
    document.querySelector('.idle-toast')?.remove();
  };
  ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'].forEach((eventName) => window.addEventListener(eventName, markActive, { passive: true }));

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
      const elapsed = Math.max(0, Math.floor((Date.now() - startedAt) / 1000) - inactiveMinutes * 60);
      readout.textContent = format(elapsed);
    }
    if (!isRunning) return;
    const idleMs = Date.now() - lastActivity;
    if (idleMs > 30 * 60 * 1000 && !warned) {
      warned = true;
      showToast();
    }
    if (idleMs > 35 * 60 * 1000) {
      inactiveMinutes += 5;
      setInactive();
      showModal();
      lastActivity = Date.now();
    }
  }, 1000);
})();
