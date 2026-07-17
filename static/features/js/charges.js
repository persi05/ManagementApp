(function () {
  const pageSelector = '.charges-page';
  const formSelector = '.charge-month-form';
  const scrollKey = 'charges-scroll-y';

  function restoreScroll() {
    const saved = sessionStorage.getItem(scrollKey);
    if (!saved) return;
    sessionStorage.removeItem(scrollKey);
    const y = Number(saved);
    if (Number.isFinite(y)) {
      window.scrollTo({ top: y, left: 0, behavior: 'auto' });
    }
  }

  function buildUrl(form) {
    const params = new URLSearchParams(new FormData(form));
    const action = form.getAttribute('action') || window.location.pathname;
    const url = new URL(action, window.location.origin);
    url.search = params.toString();
    return url;
  }

  function fallbackSubmit(form) {
    sessionStorage.setItem(scrollKey, String(window.scrollY));
    form.submit();
  }

  async function refreshCharges(form) {
    const page = document.querySelector(pageSelector);
    if (!page) {
      fallbackSubmit(form);
      return;
    }

    const url = buildUrl(form);
    const scrollY = window.scrollY;
    page.classList.add('charges-page-loading');

    try {
      const response = await fetch(url.toString(), {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
      });
      if (!response.ok) throw new Error('Unable to load charges');

      const html = await response.text();
      const doc = new DOMParser().parseFromString(html, 'text/html');
      const nextPage = doc.querySelector(pageSelector);
      if (!nextPage) throw new Error('Charges page not found');

      page.replaceWith(nextPage);
      window.history.replaceState({}, '', url.toString());
      bindChargesFilters();
      window.scrollTo({ top: scrollY, left: 0, behavior: 'auto' });
    } catch (error) {
      fallbackSubmit(form);
    }
  }

  function bindChargesFilters() {
    const form = document.querySelector(formSelector);
    if (!form || form.dataset.chargesBound === '1') return;
    form.dataset.chargesBound = '1';

    const employeeSelect = form.querySelector('select[name="employee"]');
    if (employeeSelect) {
      employeeSelect.addEventListener('change', function () {
        refreshCharges(form);
      });
    }

    form.addEventListener('submit', function () {
      sessionStorage.setItem(scrollKey, String(window.scrollY));
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    restoreScroll();
    bindChargesFilters();
  });
})();
