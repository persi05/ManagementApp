(() => {
  const timerRoot = document.querySelector('[data-timer-root]');
  if (!timerRoot) return;

  const readout = timerRoot.querySelector('[data-timer-readout]');
  const controls = timerRoot.querySelector('[data-timer-controls]');
  const initialProjectSelect = controls?.querySelector('select[name="project"]');
  const projectOptionsHtml = initialProjectSelect ? initialProjectSelect.innerHTML : '<option value="">Bez projektu</option>';
  let inactiveFields = document.querySelectorAll('[data-inactive-field]');
  const statusPill = timerRoot.querySelector('.status-pill');
  const statusUrl = timerRoot.dataset.statusUrl;
  const csrfToken = timerRoot.querySelector('input[name="csrfmiddlewaretoken"]')?.value || '';
  const nextPath = timerRoot.querySelector('input[name="next"]')?.value || window.location.pathname;
  const scrollStorageKey = `timer-scroll:${window.location.pathname}`;

  const state = {
    timerState: timerRoot.dataset.state || 'stopped',
    activeSeconds: Number(timerRoot.dataset.activeSeconds || 0),
    syncedAt: Date.now(),
  };

  let newInactiveSeconds = 0;
  let lastActivity = Date.now();
  let warned = false;
  let modalShown = false;

  const rememberScroll = () => {
    sessionStorage.setItem(scrollStorageKey, String(window.scrollY));
  };

  const restoreScroll = () => {
    const stored = sessionStorage.getItem(scrollStorageKey);
    if (stored === null) return;
    sessionStorage.removeItem(scrollStorageKey);
    window.requestAnimationFrame(() => {
      window.scrollTo({ top: Number(stored) || 0, left: 0, behavior: 'auto' });
    });
  };

  const format = (seconds) => {
    const value = Math.max(0, Math.floor(seconds));
    const h = String(Math.floor(value / 3600)).padStart(2, '0');
    const m = String(Math.floor((value % 3600) / 60)).padStart(2, '0');
    const s = String(value % 60).padStart(2, '0');
    return `${h}:${m}:${s}`;
  };

  const activeSecondsNow = () => {
    const localActiveSeconds = state.timerState === 'running'
      ? (Date.now() - state.syncedAt) / 1000
      : 0;
    return Math.max(0, state.activeSeconds + localActiveSeconds);
  };

  const displayedSeconds = () => {
    return Math.max(0, activeSecondsNow() - newInactiveSeconds);
  };

  const render = () => {
    if (readout) readout.textContent = format(displayedSeconds());
  };

  const setInactive = () => inactiveFields.forEach((field) => {
    field.value = newInactiveSeconds;
  });

  const hiddenFields = (includeInactive = false) => `
    <input type="hidden" name="csrfmiddlewaretoken" value="${csrfToken}">
    <input type="hidden" name="next" value="${nextPath}">
    ${includeInactive ? '<input type="hidden" name="inactive_seconds" data-inactive-field value="0">' : ''}
  `;

  const renderControls = () => {
    if (!controls) return;

    if (state.timerState === 'stopped') {
      controls.innerHTML = `
        <form method="post" action="${timerRoot.dataset.startUrl}" class="inline-form">
          ${hiddenFields(true)}
          <select name="project">${projectOptionsHtml}</select>
          <button class="primary-btn">Start</button>
        </form>
      `;
    } else {
      const resumeOrPause = state.timerState === 'paused'
        ? `
          <form method="post" action="${timerRoot.dataset.resumeUrl}" class="inline-form">
            ${hiddenFields(false)}
            <button class="primary-btn">Wzn&oacute;w</button>
          </form>
        `
        : `
          <form method="post" action="${timerRoot.dataset.pauseUrl}" class="inline-form">
            ${hiddenFields(true)}
            <button class="ghost-btn">Pauza</button>
          </form>
        `;

      controls.innerHTML = `
        <form method="post" action="${timerRoot.dataset.stopUrl}" class="inline-form">
          ${hiddenFields(true)}
          <button class="danger-btn">Zako&nacute;cz i zapisz</button>
        </form>
        ${resumeOrPause}
      `;
    }

    inactiveFields = document.querySelectorAll('[data-inactive-field]');
    setInactive();
    bindTimerForms();
  };

  const applyStatus = (payload) => {
    const previousTimerState = state.timerState;
    const nextTimerState = payload.state || 'stopped';
    const serverActiveSeconds = Number(payload.active_seconds || 0);
    const localActiveSeconds = activeSecondsNow();
    const canSmoothSync = state.timerState === 'running' && nextTimerState === 'running';

    state.timerState = nextTimerState;
    state.activeSeconds = canSmoothSync && Math.abs(serverActiveSeconds - localActiveSeconds) <= 2
      ? localActiveSeconds
      : serverActiveSeconds;
    state.syncedAt = Date.now();

    timerRoot.dataset.state = state.timerState;
    timerRoot.dataset.activeSeconds = String(state.activeSeconds);
    timerRoot.dataset.inactiveSeconds = String(payload.inactive_seconds || 0);
    timerRoot.dataset.startedAt = payload.started_at || '';
    timerRoot.dataset.pausedAt = payload.paused_at || '';

    if (statusPill) {
      statusPill.textContent = payload.state_label || 'Nieaktywny';
      statusPill.classList.toggle('ok', Boolean(payload.active));
    }
    if (previousTimerState !== state.timerState) {
      renderControls();
    }
    render();
  };

  const submitTimerForm = async (form) => {
    setInactive();
    rememberScroll();
    const submitButtons = form.querySelectorAll('button');
    submitButtons.forEach((button) => {
      button.disabled = true;
    });

    try {
      const response = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
      });
      if (!response.ok) {
        form.submit();
        return;
      }
      newInactiveSeconds = 0;
      applyStatus(await response.json());
      setInactive();
    } catch (error) {
      form.submit();
    }
  };

  function bindTimerForms() {
    if (!controls) return;
    controls.querySelectorAll('form').forEach((form) => {
      if (form.dataset.ajaxBound) return;
      form.dataset.ajaxBound = 'true';
      form.addEventListener('submit', (event) => {
        event.preventDefault();
        submitTimerForm(form);
      });
    });
  }

  const pollStatus = async () => {
    if (!statusUrl) return;
    try {
      const response = await fetch(statusUrl, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
      });
      if (!response.ok) return;
      applyStatus(await response.json());
    } catch (error) {
    }
  };

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
    toast.textContent = 'Brak aktywnosci. Za chwile licznik zostanie oznaczony jako nieaktywny.';
    document.body.appendChild(toast);
  };

  const showModal = () => {
    if (modalShown) return;
    modalShown = true;
    const modal = document.createElement('div');
    modal.className = 'idle-modal';
    modal.innerHTML = '<div><h2>Czy nadal pracujesz?</h2><p>Potwierdz aktywnosc, aby licznik dzialal dalej bez doliczania czasu nieaktywnego.</p><button class="primary-btn full" type="button">Pracuje dalej</button></div>';
    modal.querySelector('button').addEventListener('click', () => {
      modal.remove();
      modalShown = false;
      markActive();
    });
    document.body.appendChild(modal);
  };

  render();
  setInactive();
  bindTimerForms();
  restoreScroll();
  pollStatus();

  setInterval(() => {
    render();

    if (state.timerState !== 'running') return;

    const idleMs = Date.now() - lastActivity;
    if (idleMs > 30 * 60 * 1000 && !warned) {
      warned = true;
      showToast();
    }

    if (idleMs > 35 * 60 * 1000) {
      newInactiveSeconds += 5 * 60;
      setInactive();
      showModal();
      lastActivity = Date.now();
      state.activeSeconds = activeSecondsNow();
      state.syncedAt = Date.now();
    }
  }, 250);

  setInterval(pollStatus, 5000);
})();
