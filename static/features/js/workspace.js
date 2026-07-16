(() => {
  const storageKey = 'dcode-scroll-position';

  const rememberScroll = () => {
    try {
      sessionStorage.setItem(storageKey, JSON.stringify({
        path: window.location.pathname,
        top: window.scrollY,
        savedAt: Date.now(),
      }));
    } catch {
      // Brak sessionStorage nie powinien blokować formularza ani nawigacji.
    }
  };

  const restoreScroll = () => {
    let saved = null;
    try {
      saved = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
      sessionStorage.removeItem(storageKey);
    } catch {
      return;
    }
    if (!saved || saved.path !== window.location.pathname || Date.now() - saved.savedAt > 30000) return;
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => window.scrollTo({ top: Number(saved.top) || 0, left: 0, behavior: 'auto' }));
    });
  };

  document.addEventListener('click', (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest('a[href]');
    if (!link || link.target || link.hasAttribute('download') || link.dataset.noPreserveScroll !== undefined || link.dataset.dashboardProjectLink !== undefined) return;
    const target = new URL(link.href, window.location.href);
    const changesCurrentView = target.origin === window.location.origin
      && target.pathname === window.location.pathname
      && (target.search !== window.location.search || link.dataset.preserveScroll !== undefined);
    if (changesCurrentView) rememberScroll();
  }, true);

  let dashboardProjectRequest = null;
  document.addEventListener('click', async (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest('[data-dashboard-project-link]');
    if (!link) return;
    const currentPanel = document.querySelector('[data-client-project-panel]');
    if (!currentPanel) return;
    event.preventDefault();
    dashboardProjectRequest?.abort();
    dashboardProjectRequest = new AbortController();
    currentPanel.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(link.href, {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        signal: dashboardProjectRequest.signal,
      });
      if (!response.ok) throw new Error('Nie udało się pobrać projektu.');
      const documentFromResponse = new DOMParser().parseFromString(await response.text(), 'text/html');
      const nextPanel = documentFromResponse.querySelector('[data-client-project-panel]');
      if (!nextPanel) throw new Error('Brak podsumowania projektu.');
      currentPanel.replaceWith(nextPanel);
      window.history.replaceState({}, '', link.href);
    } catch (error) {
      if (error.name === 'AbortError') return;
      rememberScroll();
      window.location.assign(link.href);
    }
  });

  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || form.dataset.noPreserveScroll !== undefined || form.dataset.defaultProjectForm !== undefined) return;
    const action = new URL(form.action || window.location.href, window.location.href);
    const method = (form.method || 'get').toLowerCase();
    const staysOnCurrentView = action.origin === window.location.origin && action.pathname === window.location.pathname;
    if (form.dataset.preserveScroll !== undefined || staysOnCurrentView || (method === 'get' && action.pathname === window.location.pathname)) {
      rememberScroll();
    }
  }, true);

  document.addEventListener('submit', async (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || form.dataset.defaultProjectForm === undefined) return;
    event.preventDefault();
    const selectedButton = form.querySelector('button');
    if (!selectedButton || selectedButton.disabled) return;
    selectedButton.disabled = true;
    try {
      const response = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      if (!response.ok) throw new Error('Nie udało się ustawić projektu domyślnego.');
      document.querySelectorAll('[data-default-project-form]').forEach((projectForm) => {
        const button = projectForm.querySelector('button');
        if (!button) return;
        const isSelected = projectForm === form;
        button.disabled = isSelected;
        button.classList.toggle('active', isSelected);
        button.innerHTML = `<span>★</span> ${isSelected ? 'Domyślny' : 'Ustaw jako domyślny'}`;
        button.setAttribute('aria-label', isSelected
          ? `Projekt ${projectForm.dataset.projectName} jest domyślny dla zadań`
          : `Ustaw projekt ${projectForm.dataset.projectName} jako domyślny dla zadań`);
      });
    } catch {
      rememberScroll();
      HTMLFormElement.prototype.submit.call(form);
    }
  });

  restoreScroll();
})();
