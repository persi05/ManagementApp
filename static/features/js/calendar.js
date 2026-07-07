(() => {
  const dayCards = [...document.querySelectorAll('[data-selectable-day]')];
  const leaveForm = document.querySelector('[data-leave-form]');
  if (!dayCards.length || !leaveForm) return;

  const startInput = leaveForm.querySelector('input[name="start_date"]');
  const endInput = leaveForm.querySelector('input[name="end_date"]');
  const selectedRange = leaveForm.querySelector('[data-selected-range]');
  let anchorDate = null;
  let selectedDates = [];

  const cardsByDate = new Map(dayCards.map((card) => [card.dataset.selectableDay, card]));

  const datesBetween = (firstDate, secondDate) => {
    const [start, end] = [firstDate, secondDate].sort();
    return [...cardsByDate.keys()].filter((date) => date >= start && date <= end).sort();
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
    selectedDates = dates;
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

  dayCards.forEach((card) => {
    card.addEventListener('click', (event) => {
      if (event.target.closest('a')) return;
      selectDate(card.dataset.selectableDay);
    });
    card.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      selectDate(card.dataset.selectableDay);
    });
  });
})();
