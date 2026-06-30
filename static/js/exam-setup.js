(function () {
    "use strict";

    const form = document.getElementById("review-setup-form");
    if (!form) return;

    const subjectSelect = document.getElementById("id_subject");
    const topicSelect = document.getElementById("id_topic");
    const difficultySelect = document.getElementById("id_difficulty");
    const topicsApi = form.dataset.topicsApi;
    const previewApi = form.dataset.previewApi;
    const preselectedTopic = form.dataset.preselectedTopic
        || (typeof preselectedTopicId !== "undefined" && preselectedTopicId !== null
            ? String(preselectedTopicId)
            : "");
    const difficultyCards = document.getElementById("difficulty-cards");
    const summaryCount = document.getElementById("summary-question-count");
    const summarySeconds = document.getElementById("summary-seconds");

    if (!subjectSelect || !topicSelect || !difficultySelect) return;

    let previewData = null;

    function difficultyCountKey(value) {
        if (value === "easy") return "easy";
        if (value === "medium") return "medium";
        if (value === "hard") return "hard";
        return value;
    }

    function updateDifficultyCounts() {
        if (!previewData) return;
        document.querySelectorAll("[data-difficulty-count]").forEach(function (el) {
            const key = el.getAttribute("data-difficulty-count");
            const count = previewData[difficultyCountKey(key)];
            el.textContent = typeof count === "number" ? String(count) : "—";
        });
    }

    function setActiveDifficulty(value) {
        difficultySelect.value = value;
        if (!difficultyCards) return;
        difficultyCards.querySelectorAll(".select-card").forEach(function (card) {
            const active = card.dataset.difficulty === value;
            card.classList.toggle("select-card--active", active);
            card.setAttribute("aria-pressed", active ? "true" : "false");
        });
        updateSummary();
    }

    function updateSummary() {
        if (!previewData) {
            if (summaryCount) summaryCount.textContent = "—";
            if (summarySeconds) summarySeconds.textContent = "—";
            return;
        }
        const difficulty = difficultySelect.value;
        const key = difficultyCountKey(difficulty);
        const count = previewData[key];
        if (summaryCount) {
            summaryCount.textContent = typeof count === "number" ? String(count) : "—";
        }
        if (summarySeconds) {
            summarySeconds.textContent = previewData.seconds_per_question
                ? String(previewData.seconds_per_question)
                : "—";
        }
    }

    async function loadTopics(subjectId, selectTopicId) {
        topicSelect.innerHTML = '<option value="">---------</option>';
        previewData = null;
        updateDifficultyCounts();
        updateSummary();

        if (!subjectId) return;

        const resp = await fetch(topicsApi + "?subject=" + encodeURIComponent(subjectId));
        const data = await resp.json();
        (data.topics || []).forEach(function (topic) {
            const opt = document.createElement("option");
            opt.value = topic.id;
            opt.textContent = topic.name;
            topicSelect.appendChild(opt);
        });

        if (selectTopicId) {
            topicSelect.value = String(selectTopicId);
            loadPreview(topicSelect.value);
        }
    }

    async function loadPreview(topicId) {
        previewData = null;
        updateDifficultyCounts();
        updateSummary();

        if (!topicId) return;

        const resp = await fetch(previewApi + "?topic=" + encodeURIComponent(topicId));
        const data = await resp.json();
        if (!data || Object.keys(data).length === 0) return;

        previewData = data;
        updateDifficultyCounts();
        updateSummary();
    }

    subjectSelect.addEventListener("change", function () {
        loadTopics(subjectSelect.value, null);
    });

    topicSelect.addEventListener("change", function () {
        loadPreview(topicSelect.value);
    });

    if (difficultyCards) {
        difficultyCards.addEventListener("click", function (event) {
            const card = event.target.closest(".select-card[data-difficulty]");
            if (!card) return;
            setActiveDifficulty(card.dataset.difficulty);
        });
    }

    if (subjectSelect.value) {
        loadTopics(subjectSelect.value, preselectedTopic || null);
    }

    if (difficultySelect.value) {
        setActiveDifficulty(difficultySelect.value);
    } else if (difficultySelect.options.length > 1) {
        setActiveDifficulty(difficultySelect.options[1].value);
    }
})();
