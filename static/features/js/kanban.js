(() => {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content
    || document.cookie.split('; ').find((row) => row.startsWith('csrftoken='))?.split('=')[1]
    || '';
  const board = document.querySelector('.kanban-board');

  function refreshColumn(column) {
    if (!column) return;
    const taskCount = column.querySelectorAll('.kanban-card').length;
    const counter = column.querySelector('.column-count');
    if (counter) {
      counter.textContent = String(taskCount);
    }
    const modal = document.querySelector(`#edit-column-${column.dataset.column}`);
    const deleteForm = modal?.querySelector('.delete-column-form');
    const deleteNote = modal?.querySelector('.delete-column-note');
    if (deleteForm) {
      deleteForm.classList.toggle('is-hidden', taskCount > 0);
    }
    if (deleteNote) {
      deleteNote.classList.toggle('is-hidden', taskCount === 0);
    }
  }

  async function moveCard(card, targetColumn) {
    const previousDropzone = card.parentElement;
    const previousColumn = previousDropzone?.closest('.kanban-column');
    const dropzone = targetColumn.querySelector('.kanban-dropzone');
    dropzone.appendChild(card);
    refreshColumn(previousColumn);
    refreshColumn(targetColumn);

    const body = new URLSearchParams({ column: targetColumn.dataset.column });
    const response = await fetch(card.dataset.moveUrl, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrf, 'Content-Type': 'application/x-www-form-urlencoded' },
      credentials: 'same-origin',
      body,
    });

    if (!response.ok) {
      previousDropzone?.appendChild(card);
      refreshColumn(previousColumn);
      refreshColumn(targetColumn);
    }
  }

  const addColumnToggle = document.querySelector('.add-column-toggle');
  const addColumnPanel = document.querySelector('#add-column-panel');
  let activeModal = null;

  function openModal(modal) {
    if (!modal) return;
    activeModal = modal;
    modal.classList.remove('is-hidden');
    modal.querySelector('input, button, textarea, select')?.focus();
  }

  function closeModal(modal = activeModal) {
    modal?.classList.add('is-hidden');
    if (modal === activeModal) {
      activeModal = null;
    }
  }

  addColumnToggle?.addEventListener('click', () => {
    addColumnToggle.setAttribute('aria-expanded', 'true');
    openModal(addColumnPanel);
  });
  document.querySelectorAll('[data-close-add-column]').forEach((item) => {
    item.addEventListener('click', () => {
      addColumnToggle?.setAttribute('aria-expanded', 'false');
      closeModal(addColumnPanel);
    });
  });
  document.querySelectorAll('[data-open-modal]').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.preventDefault();
      openModal(document.querySelector(`#${button.dataset.openModal}`));
    });
  });
  document.querySelectorAll('[data-close-modal]').forEach((item) => {
    item.addEventListener('click', () => closeModal(item.closest('.kanban-modal')));
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      if (activeModal === addColumnPanel) {
        addColumnToggle?.setAttribute('aria-expanded', 'false');
      }
      closeModal();
    }
  });

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
      if (column.dataset.canAccept !== 'true') {
        return;
      }
      const card = document.querySelector(`.kanban-card[data-task="${event.dataTransfer.getData('text/plain')}"]`);
      if (!card) return;
      await moveCard(card, column);
    });
  });
})();
