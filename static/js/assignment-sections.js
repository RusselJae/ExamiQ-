(function () {
    "use strict";

    const form = document.getElementById("assignment-form");
    if (!form) return;

    const sectionsApi = form.dataset.sectionsApi;
    const subjectSelect = document.getElementById("id_subject");
    const termSelect = document.getElementById("id_term");
    const hiddenContainer = document.getElementById("id_program_sections");
    const groupsEl = document.getElementById("assign-section-groups");
    const placeholderEl = document.getElementById("assign-section-placeholder");
    const searchInput = document.getElementById("assign-section-search");
    const selectAllInput = document.getElementById("assign-section-select-all");
    const countEl = document.getElementById("assign-section-count");
    const submitBtn = document.getElementById("assign-section-submit");

    if (!subjectSelect || !hiddenContainer || !groupsEl) return;

    let sectionData = [];
    let searchQuery = "";

    function hiddenCheckbox(sectionId) {
        return hiddenContainer.querySelector('input[type="checkbox"][value="' + sectionId + '"]');
    }

    function isSelected(sectionId) {
        const input = hiddenCheckbox(sectionId);
        return input ? input.checked : false;
    }

    function setSelected(sectionId, checked) {
        const input = hiddenCheckbox(sectionId);
        if (input && !input.disabled) {
            input.checked = checked;
        }
    }

    function selectedCount() {
        return hiddenContainer.querySelectorAll('input[type="checkbox"]:checked').length;
    }

    function updateCount() {
        const count = selectedCount();
        const label = count === 1 ? "1 section selected" : count + " sections selected";
        if (countEl) countEl.textContent = label;
        if (submitBtn) submitBtn.disabled = count === 0;
    }

    function normalize(text) {
        return (text || "").toLowerCase().trim();
    }

    function matchesSearch(section) {
        if (!searchQuery) return true;
        const haystack = normalize(section.label) + " " + normalize(section.year);
        return haystack.indexOf(searchQuery) !== -1;
    }

    function visibleSections() {
        return sectionData.filter(function (section) {
            return matchesSearch(section) && !section.already_assigned;
        });
    }

    function syncSelectAllState() {
        if (!selectAllInput) return;
        const visible = visibleSections();
        if (!visible.length) {
            selectAllInput.checked = false;
            selectAllInput.indeterminate = false;
            selectAllInput.disabled = true;
            return;
        }
        selectAllInput.disabled = false;
        const allChecked = visible.every(function (section) {
            return isSelected(section.id);
        });
        const someChecked = visible.some(function (section) {
            return isSelected(section.id);
        });
        selectAllInput.checked = allChecked;
        selectAllInput.indeterminate = !allChecked && someChecked;
    }

    function renderGroups() {
        groupsEl.innerHTML = "";

        if (!sectionData.length) {
            const empty = document.createElement("p");
            empty.className = "assign-section-empty";
            empty.textContent = subjectSelect.value
                ? "No sections found for this subject."
                : "Select a subject to load sections.";
            groupsEl.appendChild(empty);
            syncSelectAllState();
            updateCount();
            return;
        }

        const grouped = {};
        sectionData.forEach(function (section) {
            const year = section.year || "Other";
            if (!grouped[year]) grouped[year] = [];
            grouped[year].push(section);
        });

        Object.keys(grouped).forEach(function (year) {
            const groupSections = grouped[year];
            const visibleInGroup = groupSections.some(matchesSearch);

            const group = document.createElement("div");
            group.className = "assign-section-group";
            if (!visibleInGroup) group.classList.add("assign-section-group--hidden");

            const heading = document.createElement("h3");
            heading.className = "assign-section-group__title";
            heading.textContent = year;
            group.appendChild(heading);

            const list = document.createElement("ul");
            list.className = "assign-section-list";

            groupSections.forEach(function (section) {
                const row = document.createElement("li");
                row.className = "assign-section-row";
                row.dataset.sectionId = String(section.id);
                if (!matchesSearch(section)) row.classList.add("assign-section-row--hidden");
                if (section.already_assigned) row.classList.add("assign-section-row--disabled");

                const label = document.createElement("label");
                label.className = "assign-section-row__label";

                const checkbox = document.createElement("input");
                checkbox.type = "checkbox";
                checkbox.className = "assign-section-row__checkbox";
                checkbox.value = String(section.id);
                checkbox.checked = isSelected(section.id);
                checkbox.disabled = section.already_assigned;

                const text = document.createElement("span");
                text.className = "assign-section-row__text";
                text.textContent = section.label;

                const meta = document.createElement("span");
                meta.className = "assign-section-row__meta";
                meta.textContent = section.student_count + " students";

                if (section.already_assigned) {
                    const badge = document.createElement("span");
                    badge.className = "assign-section-row__badge";
                    badge.textContent = "Assigned";
                    label.appendChild(checkbox);
                    label.appendChild(text);
                    label.appendChild(meta);
                    label.appendChild(badge);
                } else {
                    label.appendChild(checkbox);
                    label.appendChild(text);
                    label.appendChild(meta);
                }

                checkbox.addEventListener("change", function () {
                    setSelected(section.id, checkbox.checked);
                    updateCount();
                    syncSelectAllState();
                });

                row.appendChild(label);
                list.appendChild(row);
            });

            group.appendChild(list);
            groupsEl.appendChild(group);
        });

        syncSelectAllState();
        updateCount();
    }

    function flattenGroups(groups) {
        const flat = [];
        groups.forEach(function (group) {
            (group.sections || []).forEach(function (section) {
                flat.push({
                    id: section.id,
                    label: section.label,
                    student_count: section.student_count,
                    already_assigned: section.already_assigned,
                    year: group.year,
                });
            });
        });
        return flat;
    }

    async function loadSections() {
        const subjectId = subjectSelect.value;
        const termId = termSelect ? termSelect.value : "";

        sectionData = [];
        if (placeholderEl) placeholderEl.remove();

        if (!subjectId) {
            renderGroups();
            return;
        }

        groupsEl.innerHTML = '<p class="assign-section-loading">Loading sections…</p>';

        let url = sectionsApi + "?subject=" + encodeURIComponent(subjectId);
        if (termId) {
            url += "&term=" + encodeURIComponent(termId);
        }

        try {
            const resp = await fetch(url);
            const data = await resp.json();
            sectionData = flattenGroups(data.groups || []);
        } catch (err) {
            sectionData = [];
            groupsEl.innerHTML = '<p class="assign-section-empty">Could not load sections. Try again.</p>';
            updateCount();
            return;
        }

        renderGroups();
    }

    if (searchInput) {
        searchInput.addEventListener("input", function () {
            searchQuery = normalize(searchInput.value);
            renderGroups();
        });
    }

    if (selectAllInput) {
        selectAllInput.addEventListener("change", function () {
            const shouldSelect = selectAllInput.checked;
            visibleSections().forEach(function (section) {
                setSelected(section.id, shouldSelect);
            });
            renderGroups();
        });
    }

    subjectSelect.addEventListener("change", loadSections);
    if (termSelect) {
        termSelect.addEventListener("change", loadSections);
    }

    hiddenContainer.addEventListener("change", function () {
        updateCount();
        syncSelectAllState();
    });

    if (subjectSelect.value) {
        loadSections();
    } else {
        updateCount();
    }
})();
