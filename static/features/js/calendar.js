(() => {
  const dayCards = [...document.querySelectorAll('[data-selectable-day]')];
  const leaveForm = document.querySelector('[data-leave-form]');
  if (!dayCards.length || !leaveForm) return;

  const scrollKey = 'dcode-calendar-scroll';
  const monthBoard = document.querySelector('[data-calendar-today]');
  const today = monthBoard?.dataset.calendarToday || '';
  const startInput = leaveForm.querySelector('input[name="start_date"]');
  const endInput = leaveForm.querySelector('input[name="end_date"]');
  const selectedRange = leaveForm.querySelector('[data-selected-range]');
  let anchorDate = null;
  let selectedDates = [];
  let isDragging = false;
  let dragStarted = false;
  let dragAnchorDate = null;
  let suppressNextClick = false;

  const savedScroll = sessionStorage.getItem(scrollKey);
  if (savedScroll) {
    sessionStorage.removeItem(scrollKey);
    requestAnimationFrame(() => window.scrollTo(0, Number(savedScroll)));
  }

  document.querySelectorAll('[data-preserve-scroll]').forEach((form) => {
    form.addEventListener('submit', () => {
      sessionStorage.setItem(scrollKey, String(window.scrollY));
    });
  });

  const cardsByDate = new Map(dayCards.map((card) => [card.dataset.selectableDay, card]));
  let dayModal = null;

  const canSelectDate = (date) => {
    const card = cardsByDate.get(date);
    return Boolean(card && date >= today && card.dataset.approvedLeave !== '1');
  };

  const datesBetween = (firstDate, secondDate) => {
    const [start, end] = [firstDate, secondDate].sort();
    return [...cardsByDate.keys()].filter((date) => date >= start && date <= end && canSelectDate(date)).sort();
  };

  const clearSelection = () => {
    selectedDates = [];
    anchorDate = null;
    dayCards.forEach((card) => card.classList.remove('is-selected'));
    leaveForm.classList.add('is-hidden');
    if (startInput) startInput.value = '';
    if (endInput) endInput.value = '';
  };

  const applySelection = (dates) => {
    selectedDates = dates.filter(canSelectDate);
    dayCards.forEach((card) => {
      card.classList.toggle('is-selected', selectedDates.includes(card.dataset.selectableDay));
    });

    if (!selectedDates.length) {
      clearSelection();
      return;
    }

    const start = selectedDates[0];
    const end = selectedDates[selectedDates.length - 1];
    if (startInput) startInput.value = start;
    if (endInput) endInput.value = end;
    if (selectedRange) {
      selectedRange.textContent = start === end
        ? `Wybrany dzień: ${start}`
        : `Wybrany zakres: ${start} - ${end}`;
    }
    leaveForm.classList.remove('is-hidden');
  };

  const selectDate = (date) => {
    if (selectedDates.length === 1 && selectedDates[0] === date) {
      clearSelection();
      return;
    }

    if (!anchorDate || selectedDates.length > 1) {
      anchorDate = date;
      applySelection([date]);
      return;
    }

    applySelection(datesBetween(anchorDate, date));
  };

  const closeDayModal = () => {
    dayModal?.remove();
    dayModal = null;
  };

  const daySummary = (card) => {
    const notes = (card.querySelector('.day-notes-full') || card.querySelector('.day-notes'))?.cloneNode(true);
    notes?.removeAttribute('hidden');
    if (!notes || !notes.textContent.trim()) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.textContent = 'Brak wpisów na ten dzień.';
      return empty;
    }
    return notes;
  };

  const openDayModal = (card) => {
    closeDayModal();
    const date = card.dataset.selectableDay;
    const isPast = date < today;
    const hasApprovedLeave = card.dataset.approvedLeave === '1';
    const dayNumber = card.querySelector('.day-card-header strong')?.textContent?.trim() || date;
    const monthName = card.querySelector('.day-card-header small')?.textContent?.trim() || '';

    dayModal = document.createElement('div');
    dayModal.className = 'calendar-day-modal';
    dayModal.innerHTML = `
      <div class="calendar-day-modal-backdrop" data-close-day-modal></div>
      <section class="calendar-day-modal-card" role="dialog" aria-modal="true" aria-label="Szczegóły dnia">
        <button class="ghost-btn small-btn calendar-day-modal-close" type="button" data-close-day-modal>Zamknij</button>
        <div class="panel-head">
          <div>
            <h2>${dayNumber} ${monthName}</h2>
            <p>${date}</p>
          </div>
        </div>
        <div class="calendar-day-modal-content"></div>
        ${
          isPast || hasApprovedLeave
            ? `<p class="calendar-day-modal-note">${hasApprovedLeave ? 'Ten dzień ma już zaakceptowane wolne.' : 'Nie można brać wolnego w przeszłości.'}</p>`
            : '<button class="primary-btn full" type="button" data-take-day-leave>Weź wolne</button>'
        }
      </section>
    `;

    dayModal.querySelector('.calendar-day-modal-content').appendChild(daySummary(card));
    dayModal.querySelectorAll('[data-close-day-modal]').forEach((button) => {
      button.addEventListener('click', closeDayModal);
    });
    dayModal.querySelector('[data-take-day-leave]')?.addEventListener('click', () => {
      if (startInput) startInput.value = date;
      if (endInput) endInput.value = date;
      closeDayModal();
      if (leaveForm.requestSubmit) {
        leaveForm.requestSubmit();
      } else {
        leaveForm.submit();
      }
    });
    document.body.appendChild(dayModal);
  };

  const selectableCardFromPoint = (clientX, clientY) => {
    const element = document.elementFromPoint(clientX, clientY);
    return element?.closest?.('[data-selectable-day]');
  };

  const beginDrag = (card) => {
    dragAnchorDate = card.dataset.selectableDay;
    if (!canSelectDate(dragAnchorDate)) return;
    isDragging = true;
    dragStarted = false;
    anchorDate = dragAnchorDate;
  };

  const updateDrag = (card) => {
    if (!isDragging || !card) return;
    const date = card.dataset.selectableDay;
    if (!date || date === selectedDates[selectedDates.length - 1]) return;
    dragStarted = true;
    applySelection(datesBetween(dragAnchorDate, date));
  };

  const finishDrag = () => {
    if (!isDragging) return;
    suppressNextClick = dragStarted;
    isDragging = false;
    dragStarted = false;
    dragAnchorDate = null;
  };

  dayCards.forEach((card) => {
    card.addEventListener('pointerdown', (event) => {
      if (event.button !== 0 || event.target.closest('a')) return;
      event.preventDefault();
      card.setPointerCapture?.(event.pointerId);
      beginDrag(card);
    });
    card.addEventListener('pointerenter', () => {
      updateDrag(card);
    });
    card.addEventListener('pointermove', (event) => {
      updateDrag(selectableCardFromPoint(event.clientX, event.clientY));
    });
    card.addEventListener('pointerup', () => {
      finishDrag();
    });
    card.addEventListener('pointercancel', () => {
      finishDrag();
    });
    card.addEventListener('click', (event) => {
      if (event.target.closest('a')) return;
      if (suppressNextClick) {
        suppressNextClick = false;
        return;
      }
      openDayModal(card);
    });
    card.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      openDayModal(card);
    });
  });

  window.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeDayModal();
  });
})();
