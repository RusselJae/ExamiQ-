/**
 * Batch question draft — sessionStorage persistence for add-questions flow.
 */
(function () {
    "use strict";

    const LETTERS = ["A", "B", "C", "D"];

    function draftKey(coursePk) {
        return "examiq.batch-draft." + coursePk;
    }

    function emptyDraft() {
        return {
            settings: {
                yearLevel: "",
                subjectId: "",
                topicId: "",
                difficulty: "",
            },
            questions: [],
            questionIndex: 0,
        };
    }

    function loadDraft(coursePk) {
        try {
            const raw = sessionStorage.getItem(draftKey(coursePk));
            if (!raw) return emptyDraft();
            const parsed = JSON.parse(raw);
            return {
                settings: Object.assign({}, emptyDraft().settings, parsed.settings || {}),
                questions: Array.isArray(parsed.questions) ? parsed.questions : [],
                questionIndex: parsed.questionIndex || 0,
            };
        } catch (e) {
            return emptyDraft();
        }
    }

    function saveDraft(coursePk, draft) {
        try {
            sessionStorage.setItem(draftKey(coursePk), JSON.stringify(draft));
        } catch (e) { /* ignore quota */ }
    }

    function clearDraft(coursePk) {
        try {
            sessionStorage.removeItem(draftKey(coursePk));
        } catch (e) { /* ignore */ }
    }

    function draftFromDom(config) {
        const draft = emptyDraft();
        draft.settings.yearLevel = config.yearSelect.value || "";
        draft.settings.subjectId = config.subjectSelect.value || "";
        draft.settings.topicId = config.topicSelect.value || "";
        draft.settings.difficulty = config.difficultySelect.value || "";
        draft.questionIndex = config.questionIndex;
        draft.questions = [];
        for (let i = 0; i < config.questionIndex; i++) {
            draft.questions.push(config.getQuestionData(i));
        }
        return draft;
    }

    function syncDomFromDraft(config, draft) {
        if (draft.settings.yearLevel) {
            config.yearSelect.value = draft.settings.yearLevel;
        }
        if (draft.settings.difficulty) {
            config.difficultySelect.value = draft.settings.difficulty;
        }
        config.fieldsStore.innerHTML = "";
        config.tableBody.innerHTML = "";
        config.questionIndex = draft.questionIndex || draft.questions.length;
        for (let i = 0; i < config.questionIndex; i++) {
            const data = draft.questions[i] || {
                stem: "",
                correct: "A",
                concept: "",
                choices: { A: "", B: "", C: "", D: "" },
            };
            config.ensureFieldsForIndex(i);
            config.setQuestionData(i, data);
            config.renderTableRow(i);
        }
        config.syncCountInput();
    }

    function removeQuestion(config, index) {
        const wrappers = config.fieldsStore.querySelectorAll("[data-index]");
        const rows = config.tableBody.querySelectorAll("tr[data-index]");
        const questions = [];
        for (let i = 0; i < config.questionIndex; i++) {
            if (i !== index) {
                questions.push(config.getQuestionData(i));
            }
        }
        config.fieldsStore.innerHTML = "";
        config.tableBody.innerHTML = "";
        config.questionIndex = questions.length;
        questions.forEach(function (data, i) {
            config.ensureFieldsForIndex(i);
            config.setQuestionData(i, data);
            config.renderTableRow(i);
        });
        config.syncCountInput();
        persist(config);
    }

    function persist(config) {
        saveDraft(config.coursePk, draftFromDom(config));
    }

    function trashIconSvg() {
        return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2m-1 0v14H9V6"/></svg>';
    }

    window.ExamiQBatch = {
        LETTERS: LETTERS,
        loadDraft: loadDraft,
        saveDraft: saveDraft,
        clearDraft: clearDraft,
        draftFromDom: draftFromDom,
        syncDomFromDraft: syncDomFromDraft,
        removeQuestion: removeQuestion,
        persist: persist,
        trashIconSvg: trashIconSvg,
    };
})();
