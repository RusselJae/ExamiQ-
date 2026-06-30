(function () {
    "use strict";

    const form = document.getElementById("professor-exam-setup-form");
    if (!form) return;

    const enabledInput = document.getElementById("id_is_enabled");
    const availabilityPill = document.getElementById("exam-availability-pill");
    const difficultyContainer = document.getElementById("exam-difficulty-cards");
    const topicCardsEl = document.getElementById("exam-topic-cards");
    const topicCounter = document.getElementById("exam-topic-counter");

    function difficultyCheckboxes() {
        return Array.prototype.slice.call(form.querySelectorAll('input[name="allowed_difficulties"]'));
    }

    function topicCheckboxes() {
        return Array.prototype.slice.call(form.querySelectorAll('input[name="topics"]'));
    }

    function syncAvailabilityPill() {
        if (!enabledInput || !availabilityPill) return;
        const enabled = enabledInput.checked;
        const enabledLabel = availabilityPill.dataset.enabledLabel || "Exam enabled";
        const disabledLabel = availabilityPill.dataset.disabledLabel || "Exam disabled";
        const text = availabilityPill.querySelector(".exam-setup-availability-pill__text");
        availabilityPill.classList.toggle("exam-setup-availability-pill--on", enabled);
        availabilityPill.setAttribute("aria-pressed", enabled ? "true" : "false");
        if (text) text.textContent = enabled ? enabledLabel : disabledLabel;
    }

    function syncDifficultyCards() {
        if (!difficultyContainer) return;
        const checked = new Set(
            difficultyCheckboxes()
                .filter(function (input) { return input.checked; })
                .map(function (input) { return input.value; })
        );
        difficultyContainer.querySelectorAll(".select-card[data-difficulty]").forEach(function (card) {
            const active = checked.has(card.dataset.difficulty);
            card.classList.toggle("select-card--active", active);
            card.setAttribute("aria-pressed", active ? "true" : "false");
        });
    }

    function toggleDifficulty(value) {
        const input = difficultyCheckboxes().find(function (el) {
            return el.value === value;
        });
        if (!input) return;
        input.checked = !input.checked;
        syncDifficultyCards();
    }

    function buildTopicCards() {
        if (!topicCardsEl) return;
        topicCardsEl.innerHTML = "";
        const boxes = topicCheckboxes();
        boxes.forEach(function (input) {
            const label = input.closest("label");
            const name = label ? label.textContent.trim() : "Topic " + input.value;
            const card = document.createElement("button");
            card.type = "button";
            card.className = "select-card exam-setup-topic-card";
            card.dataset.topicId = input.value;
            card.setAttribute("aria-pressed", input.checked ? "true" : "false");
            if (input.checked) card.classList.add("select-card--active");
            card.textContent = name;
            card.addEventListener("click", function () {
                input.checked = !input.checked;
                card.classList.toggle("select-card--active", input.checked);
                card.setAttribute("aria-pressed", input.checked ? "true" : "false");
                updateTopicCounter();
            });
            topicCardsEl.appendChild(card);
        });
        updateTopicCounter();
    }

    function updateTopicCounter() {
        if (!topicCounter) return;
        const boxes = topicCheckboxes();
        const selected = boxes.filter(function (input) { return input.checked; }).length;
        topicCounter.textContent = selected + " of " + boxes.length + " selected";
    }

    if (availabilityPill && enabledInput) {
        availabilityPill.addEventListener("click", function () {
            enabledInput.checked = !enabledInput.checked;
            syncAvailabilityPill();
        });
        syncAvailabilityPill();
    }

    if (difficultyContainer) {
        difficultyContainer.addEventListener("click", function (event) {
            const card = event.target.closest(".select-card[data-difficulty]");
            if (!card) return;
            toggleDifficulty(card.dataset.difficulty);
        });
        syncDifficultyCards();
    }

    buildTopicCards();
})();
