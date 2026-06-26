(function() {
    function initQuestionTimer() {
        const card = document.getElementById("question-card");
        if (!card || card.dataset.timedExam !== "true") return;

        const total = parseInt(card.dataset.seconds, 10) || 30;
        let remaining = total;
        const display = document.getElementById("question-timer-display");
        const ring = document.getElementById("question-timer-ring");
        const timeSpentInput = document.getElementById("time-spent");
        const timedOutInput = document.getElementById("timed-out-input");
        const form = document.getElementById("answer-form");
        if (!display || !form) return;

        let elapsed = 0;
        let intervalId = null;

        function updateUI() {
            display.textContent = remaining;
            if (timeSpentInput) timeSpentInput.value = elapsed;
            const secondsLabel = document.getElementById("question-timer-seconds");
            if (secondsLabel) secondsLabel.textContent = remaining;
            card.classList.remove("timer-warning", "timer-critical");
            ring.classList.remove("timer-urgent", "timer-critical-ring");
            if (remaining <= 5) {
                card.classList.add("timer-critical");
                ring.classList.add("timer-critical-ring");
            } else if (remaining <= 10) {
                card.classList.add("timer-warning");
                ring.classList.add("timer-urgent");
            }
        }

        function autoSubmit() {
            if (intervalId) clearInterval(intervalId);
            if (timedOutInput) timedOutInput.value = "true";
            if (timeSpentInput) timeSpentInput.value = total;
            if (typeof htmx !== "undefined") {
                htmx.trigger(form, "submit");
            } else {
                form.submit();
            }
        }

        updateUI();
        intervalId = setInterval(function() {
            elapsed += 1;
            remaining -= 1;
            updateUI();
            if (remaining <= 0) {
                autoSubmit();
            }
        }, 1000);

        form.addEventListener("submit", function() {
            if (intervalId) clearInterval(intervalId);
            if (timeSpentInput && !timedOutInput.value) {
                timeSpentInput.value = elapsed;
            }
        });
    }

    document.addEventListener("DOMContentLoaded", initQuestionTimer);
    document.body.addEventListener("htmx:afterSwap", function(event) {
        if (event.detail.target && event.detail.target.id === "question-container") {
            initQuestionTimer();
        }
    });
})();
