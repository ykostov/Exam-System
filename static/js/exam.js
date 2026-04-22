/**
 * Exam countdown timer.
 * Auto-submits the form when time expires (integrity enforcement).
 */
function startTimer(totalSeconds, displayEl, formEl) {
  let remaining = totalSeconds;

  function update() {
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;
    displayEl.textContent =
      String(mins).padStart(2, '0') + ':' + String(secs).padStart(2, '0');

    // Visual warnings
    if (remaining <= 60) {
      displayEl.classList.add('critical');
      displayEl.classList.remove('warning');
    } else if (remaining <= 300) {
      displayEl.classList.add('warning');
    }

    if (remaining <= 0) {
      clearInterval(interval);
      displayEl.textContent = '00:00';
      // Auto-submit (integrity: server also validates time)
      formEl.submit();
      return;
    }
    remaining--;
  }

  update();
  const interval = setInterval(update, 1000);
}
