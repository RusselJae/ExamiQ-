(function() {
    const TIMER_RADIUS = 45;
    const TIMER_CIRCUMFERENCE = 2 * Math.PI * TIMER_RADIUS;
    let activeTimerCleanup = null;

    function cleanupActiveTimer() {
        if (activeTimerCleanup) {
            activeTimerCleanup();
            activeTimerCleanup = null;
        }
    }

    function initQuestionTimer() {
        cleanupActiveTimer();

        const card = document.getElementById("question-card");
        if (!card || card.dataset.timedExam !== "true") return;

        const total = parseInt(card.dataset.seconds, 10) || 30;
        let remaining = total;
        const display = document.getElementById("question-timer-display");
        const ring = document.getElementById("question-timer-ring");
        const progressRing = document.getElementById("question-timer-progress");
        const timeSpentInput = document.getElementById("time-spent");
        const timedOutInput = document.getElementById("timed-out-input");
        const form = document.getElementById("answer-form");
        if (!display || !form) return;

        if (progressRing) {
            progressRing.style.strokeDasharray = String(TIMER_CIRCUMFERENCE);
            progressRing.style.strokeDashoffset = "0";
            void progressRing.getBoundingClientRect();
            progressRing.style.strokeDashoffset = String(TIMER_CIRCUMFERENCE);
        }

        if (ring) {
            ring.classList.remove("exam-timer-wrap--enter");
            void ring.offsetWidth;
            ring.classList.add("exam-timer-wrap--enter");
            ring.addEventListener("animationend", function onEnter() {
                ring.classList.remove("exam-timer-wrap--enter");
                ring.removeEventListener("animationend", onEnter);
            });
        }

        let elapsed = 0;
        let intervalId = null;

        function updateRing() {
            if (!progressRing || total <= 0) return;
            const fraction = Math.max(0, Math.min(1, remaining / total));
            progressRing.style.strokeDashoffset = String(TIMER_CIRCUMFERENCE * (1 - fraction));
        }

        function updateUI() {
            display.textContent = remaining;
            if (timeSpentInput) timeSpentInput.value = elapsed;
            updateRing();

            card.classList.remove("timer-warning", "timer-critical");
            if (ring) ring.classList.remove("timer-urgent", "timer-critical-ring");
            if (progressRing) progressRing.classList.remove("exam-timer-svg__progress--warning", "exam-timer-svg__progress--critical");

            if (remaining <= 5) {
                card.classList.add("timer-critical");
                if (ring) ring.classList.add("timer-critical-ring");
                if (progressRing) progressRing.classList.add("exam-timer-svg__progress--critical");
            } else if (remaining <= 10) {
                card.classList.add("timer-warning");
                if (ring) ring.classList.add("timer-urgent");
                if (progressRing) progressRing.classList.add("exam-timer-svg__progress--warning");
            }
        }

        function autoSubmit() {
            if (intervalId) clearInterval(intervalId);
            intervalId = null;
            if (timedOutInput) timedOutInput.value = "true";
            if (timeSpentInput) timeSpentInput.value = total;
            if (typeof htmx !== "undefined") {
                htmx.trigger(form, "submit");
            } else {
                form.submit();
            }
        }

        function onFormSubmit() {
            if (intervalId) clearInterval(intervalId);
            intervalId = null;
            if (timeSpentInput && timedOutInput && timedOutInput.value !== "true") {
                timeSpentInput.value = elapsed;
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

        form.addEventListener("submit", onFormSubmit);

        activeTimerCleanup = function() {
            if (intervalId) clearInterval(intervalId);
            intervalId = null;
            form.removeEventListener("submit", onFormSubmit);
        };

        window.stopQuestionTimer = function() {
            if (intervalId) clearInterval(intervalId);
            intervalId = null;
            if (timeSpentInput && timedOutInput && timedOutInput.value !== "true") {
                timeSpentInput.value = elapsed;
            }
        };
    }

    document.addEventListener("DOMContentLoaded", initQuestionTimer);

    document.body.addEventListener("htmx:beforeSwap", function(event) {
        if (event.detail.target && event.detail.target.id === "question-container") {
            cleanupActiveTimer();
        }
    });

    document.body.addEventListener("htmx:afterSwap", function(event) {
        if (event.detail.target && event.detail.target.id === "question-container") {
            initQuestionTimer();
        }
    });
})();
