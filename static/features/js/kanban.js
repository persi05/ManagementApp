(() => {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content
    || document.cookie.split('; ').find((row) => row.startsWith('csrftoken='))?.split('=')[1]
    || '';
  const board = document.querySelector('.kanban-board');
  const maxMovePosition = board?.dataset?.maxMovePosition === undefined || board?.dataset?.maxMovePosition === ''
    ? null
    : Number(board.dataset.maxMovePosition);

  async function moveCard(card, targetColumn) {
    const previousDropzone = card.parentElement;
    const dropzone = targetColumn.querySelector('.kanban-dropzone');
    dropzone.appendChild(card);

    const body = new URLSearchParams({ column: targetColumn.dataset.column });
    const response = await fetch(card.dataset.moveUrl, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrf, 'Content-Type': 'application/x-www-form-urlencoded' },
      credentials: 'same-origin',
      body,
    });

    if (!response.ok) {
      previousDropzone?.appendChild(card);
    }
  }

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
