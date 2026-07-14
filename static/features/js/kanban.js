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
  const addTaskToggles = Array.from(document.querySelectorAll('.add-task-toggle'));
  const addTaskPanel = document.querySelector('#new-task-panel');
  const taskForm = document.querySelector('[data-task-form]');
  let activeModal = null;

  document.querySelectorAll('form').forEach((form) => {
    form.addEventListener('submit', () => {
      const submitter = form.querySelector('button[type="submit"], button:not([type]), input[type="submit"]');
      if (submitter) {
        submitter.disabled = true;
        submitter.dataset.originalText = submitter.textContent || submitter.value || '';
        if (submitter.tagName === 'BUTTON') {
          submitter.textContent = 'Zapisywanie...';
        }
      }
    });
  });

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
  function setTaskColumn(columnId) {
    if (!taskForm || !columnId) return;
    let field = taskForm.querySelector('[name="column"]');
    if (!field) {
      field = document.createElement('input');
      field.type = 'hidden';
      field.name = 'column';
      taskForm.appendChild(field);
    }
    field.value = columnId;
  }

  addTaskToggles.forEach((toggle) => {
    toggle.addEventListener('click', () => {
      addTaskToggles.forEach((item) => item.setAttribute('aria-expanded', 'false'));
      toggle.setAttribute('aria-expanded', 'true');
      setTaskColumn(toggle.dataset.taskColumn);
      openModal(addTaskPanel);
    });
  });
  document.querySelectorAll('[data-close-add-column]').forEach((item) => {
    item.addEventListener('click', () => {
      addColumnToggle?.setAttribute('aria-expanded', 'false');
      closeModal(addColumnPanel);
    });
  });
  document.querySelectorAll('[data-close-add-task]').forEach((item) => {
    item.addEventListener('click', () => {
      addTaskToggles.forEach((toggle) => toggle.setAttribute('aria-expanded', 'false'));
      closeModal(addTaskPanel);
    });
  });
  document.querySelectorAll('[data-open-modal]').forEach((button) => {
    button.addEventListener('click', (event) => {
      if (button !== event.target && event.target.closest('a, button, input, textarea, select, label')) {
        return;
      }
      event.preventDefault();
      openModal(document.querySelector(`#${button.dataset.openModal}`));
    });
    button.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') {
        return;
      }
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
      if (activeModal === addTaskPanel) {
        addTaskToggles.forEach((toggle) => toggle.setAttribute('aria-expanded', 'false'));
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

  document.querySelectorAll('[data-label-transfer]').forEach((root) => {
    const form = root.closest('form');
    const hidden = form?.querySelector('input[type="hidden"][name="labels"]');
    const selectedBox = root.querySelector('[data-label-selected]');
    const availableBox = root.querySelector('[data-label-available]');
    const newInput = root.querySelector('[data-label-new]');
    const addButton = root.querySelector('[data-label-add]');

    function labelsIn(box) {
      return Array.from(box.querySelectorAll('[data-label-item]')).map((item) => item.dataset.labelValue);
    }

    function syncHidden() {
      if (hidden) {
        hidden.value = labelsIn(selectedBox).join(', ');
      }
    }

    function ensureEmptyState(box) {
      const hasItems = Boolean(box.querySelector('[data-label-item]'));
      let empty = box.querySelector('.label-transfer-empty');
      if (hasItems && empty) {
        empty.remove();
      }
      if (!hasItems && !empty) {
        empty = document.createElement('button');
        empty.type = 'button';
        empty.disabled = true;
        empty.className = 'label-transfer-empty';
        empty.textContent = 'Brak';
        box.appendChild(empty);
      }
    }

    function normalizeLabel(value) {
      return value.trim().toLowerCase();
    }

    function createItem(label, group) {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'label-transfer-item';
      item.dataset.labelItem = '';
      item.dataset.labelGroup = group;
      item.dataset.labelValue = label;
      item.textContent = label;
      return item;
    }

    function moveItem(item, targetBox, group) {
      if (!item || targetBox.querySelector(`[data-label-value="${CSS.escape(item.dataset.labelValue)}"]`)) return;
      item.classList.remove('active');
      item.dataset.labelGroup = group;
      targetBox.appendChild(item);
    }

    function moveActiveItems(sourceBox, targetBox, group) {
      const activeItems = Array.from(sourceBox.querySelectorAll('[data-label-item].active'));
      activeItems.forEach((item) => moveItem(item, targetBox, group));
      ensureEmptyState(selectedBox);
      ensureEmptyState(availableBox);
      syncHidden();
    }

    root.addEventListener('click', (event) => {
      const item = event.target.closest('[data-label-item]');
      if (item && root.contains(item)) {
        item.classList.toggle('active');
        return;
      }

      const move = event.target.closest('[data-label-move]')?.dataset.labelMove;
      if (move === 'left') {
        moveActiveItems(availableBox, selectedBox, 'selected');
      }
      if (move === 'right') {
        moveActiveItems(selectedBox, availableBox, 'available');
      }
    });

    addButton?.addEventListener('click', () => {
      const label = normalizeLabel(newInput?.value || '');
      if (!label) return;
      if (!availableBox.querySelector(`[data-label-value="${CSS.escape(label)}"]`) && !selectedBox.querySelector(`[data-label-value="${CSS.escape(label)}"]`)) {
        availableBox.appendChild(createItem(label, 'available'));
      }
      if (newInput) {
        newInput.value = '';
        newInput.focus();
      }
      ensureEmptyState(availableBox);
    });

    newInput?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        addButton?.click();
      }
    });
    newInput?.addEventListener('click', (event) => event.stopPropagation());
    newInput?.addEventListener('pointerdown', (event) => event.stopPropagation());

    ensureEmptyState(selectedBox);
    ensureEmptyState(availableBox);
    syncHidden();
    form?.addEventListener('submit', syncHidden, { capture: true });
  });
})();
