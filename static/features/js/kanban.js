(() => {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content
    || document.cookie.split('; ').find((row) => row.startsWith('csrftoken='))?.split('=')[1]
    || '';
  const board = document.querySelector('.kanban-board');
  const maxMovePosition = board?.dataset?.maxMovePosition === undefined || board?.dataset?.maxMovePosition === ''
    ? null
    : Number(board.dataset.maxMovePosition);

  function refreshColumn(column) {
    if (!column) return;
    const taskCount = column.querySelectorAll('.kanban-card').length;
    const counter = column.querySelector('.column-count');
    const deleteForm = column.querySelector('.delete-column-form');
    if (counter) {
      counter.textContent = String(taskCount);
    }
    if (deleteForm) {
      deleteForm.classList.toggle('is-hidden', taskCount > 0);
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
  function openAddColumnModal() {
    addColumnPanel?.classList.remove('is-hidden');
    addColumnToggle?.setAttribute('aria-expanded', 'true');
    addColumnPanel?.querySelector('input[name="name"]')?.focus();
  }

  function closeAddColumnModal() {
    addColumnPanel?.classList.add('is-hidden');
    addColumnToggle?.setAttribute('aria-expanded', 'false');
  }

  addColumnToggle?.addEventListener('click', openAddColumnModal);
  document.querySelectorAll('[data-close-add-column]').forEach((item) => {
    item.addEventListener('click', closeAddColumnModal);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeAddColumnModal();
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
      const targetPosition = Number(column.dataset.columnPosition);
      if (Number.isFinite(maxMovePosition) && targetPosition > maxMovePosition) {
        return;
      }
      const card = document.querySelector(`.kanban-card[data-task="${event.dataTransfer.getData('text/plain')}"]`);
      if (!card) return;
      await moveCard(card, column);
    });
  });
})();
