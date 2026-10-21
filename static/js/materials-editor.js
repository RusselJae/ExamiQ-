/**
 * Document editor for learning materials.
 *
 * A contenteditable surface styled as a document page, with a small toolbar
 * for the structure a DOCX actually carries (headings, lists, bold/italic,
 * quotes). On save the inner HTML is posted to `content_html`, where the server
 * sanitizes it and re-derives the plain text AI retrieval reads.
 */
(function () {
    "use strict";

    var BLOCK_TAGS = ["P", "H1", "H2", "H3", "H4", "H5", "H6", "LI", "BLOCKQUOTE", "PRE"];

    function closestBlock(node) {
        while (node && node !== document.body) {
            if (node.nodeType === 1 && BLOCK_TAGS.indexOf(node.nodeName) !== -1) {
                return node;
            }
            node = node.parentNode;
        }
        return null;
    }

    function hasTag(container, tag) {
        if (!container) return false;
        var name = tag.toUpperCase();
        while (container && container !== document.body) {
            if (container.nodeType === 1 && container.nodeName === name) return true;
            container = container.parentNode;
        }
        return false;
    }

    function initEditor(root) {
        if (!root || root.dataset.editorBound === "1") return;
        var form = root.matches("[data-editor-form]")
            ? root
            : root.querySelector("[data-editor-form]");
        var scope = form || root;
        var surface = scope.querySelector("[data-editor-surface]");
        var payload = scope.querySelector("[data-editor-payload]");
        var toolbar = scope.querySelector("[data-editor-toolbar]");
        var revertBtn = scope.querySelector("[data-editor-revert]");
        var countEl = scope.querySelector("[data-editor-count]");
        if (!form || !surface || !payload) return;
        root.dataset.editorBound = "1";

        function serialize() {
            return surface.innerHTML.trim();
        }

        var original = serialize();

        function textStats() {
            var text = (surface.innerText || "").trim();
            return {
                words: text ? text.split(/\s+/).length : 0,
                chars: text.length,
            };
        }

        function renderCount() {
            if (!countEl) return;
            var stats = textStats();
            countEl.textContent =
                stats.words.toLocaleString() +
                (stats.words === 1 ? " word" : " words") +
                " · " +
                stats.chars.toLocaleString() +
                " characters";
        }

        function syncToolbarState() {
            if (!toolbar) return;
            var selection = window.getSelection();
            var anchor = selection ? selection.anchorNode : null;
            var block = closestBlock(anchor);
            toolbar.querySelectorAll("[data-cmd]").forEach(function (btn) {
                var tag = btn.getAttribute("data-cmd").toUpperCase();
                var on;
                if (tag === "BOLD") {
                    // Bold is inline, so look for the tag around the caret
                    // rather than for a block-level ancestor.
                    on = hasTag(anchor, "B") || hasTag(anchor, "STRONG");
                } else if (tag === "ITALIC") {
                    on = hasTag(anchor, "I") || hasTag(anchor, "EM");
                } else {
                    on = hasTag(block, tag);
                }
                btn.classList.toggle("is-active", !!on);
            });
            toolbar.querySelectorAll("[data-block]").forEach(function (btn) {
                var tag = btn.getAttribute("data-block").toUpperCase();
                var on = block && block.nodeName === tag;
                if (tag === "UL" || tag === "OL") {
                    on = hasTag(block, tag);
                }
                btn.classList.toggle("is-active", !!on);
            });
        }

        function setDirty(dirty) {
            root.classList.toggle("is-dirty", dirty);
            if (revertBtn) revertBtn.classList.toggle("hidden", !dirty);
            if (window.ExamiQMaterials && window.ExamiQMaterials.setSaveStatus) {
                window.ExamiQMaterials.setSaveStatus(dirty ? "dirty" : "saved");
            }
        }

        function sync() {
            setDirty(serialize() !== original);
            renderCount();
            syncToolbarState();
        }

        /* Remember the current selection so a toolbar click can restore it:
           focusing the surface collapses the selection, which would make the
           command apply to the caret instead of the selected text. */
        var savedRange = null;

        function rememberSelection() {
            var selection = window.getSelection();
            if (!selection || selection.rangeCount === 0) return;
            var range = selection.getRangeAt(0);
            if (!surface.contains(range.commonAncestorContainer)) return;
            savedRange = range.cloneRange();
        }

        function restoreSelection() {
            if (!savedRange) return;
            var selection = window.getSelection();
            if (!selection) return;
            try {
                selection.removeAllRanges();
                selection.addRange(savedRange);
            } catch (err) {
                /* ignore */
            }
        }

        function exec(command, value) {
            rememberSelection();
            surface.focus();
            restoreSelection();
            try {
                document.execCommand(command, false, value || null);
            } catch (err) {
                /* command unsupported in this browser; nothing to do */
            }
            sync();
        }

        function ensureSelectionInSurface() {
            var selection = window.getSelection();
            if (!selection || selection.rangeCount === 0) return false;
            var range = selection.getRangeAt(0);
            return surface.contains(range.commonAncestorContainer);
        }

        function applyBlock(tag) {
            if (!ensureSelectionInSurface()) {
                surface.focus();
            }
            var selection = window.getSelection();
            var block = closestBlock(selection ? selection.anchorNode : null);

            if (tag === "UL" || tag === "OL") {
                if (block && block.parentNode && block.parentNode.nodeName === tag) {
                    // Already in this list: unwrap back to paragraphs.
                    var items = block.parentNode.children;
                    while (items.length) {
                        var li = items[0];
                        var para = document.createElement("p");
                        while (li.firstChild) para.appendChild(li.firstChild);
                        block.parentNode.parentNode.insertBefore(para, block.parentNode);
                        block.parentNode.removeChild(li);
                    }
                    sync();
                } else {
                    exec("insertUnorderedList");
                }
                return;
            }

            if (tag === "BLOCKQUOTE") {
                exec("formatBlock", "<blockquote>");
                return;
            }

            if (block) {
                var replacement = document.createElement(
                    block.nodeName === tag ? "P" : tag
                );
                while (block.firstChild) replacement.appendChild(block.firstChild);
                if (block.parentNode) block.parentNode.replaceChild(replacement, block);
                // Keep the caret where the user was working.
                placeCaretAtEnd(replacement);
                sync();
            } else {
                exec("formatBlock", "<" + tag.toLowerCase() + ">");
            }
        }

        function placeCaretAtEnd(node) {
            var selection = window.getSelection();
            if (!selection) return;
            var range = document.createRange();
            try {
                range.selectNodeContents(node);
                range.collapse(false);
                selection.removeAllRanges();
                selection.addRange(range);
            } catch (err) {
                /* ignore */
            }
        }

        /* The editor lives inside the document form: the single "Save" button
           posts both the metadata and the edited content. */
        function collectContent() {
            if (serialize() === original) {
                payload.value = "";
                return true;
            }
            if (!(surface.innerText || "").trim()) {
                if (window.showToast) {
                    window.showToast("Add some content before saving.", "warning");
                }
                return false;
            }
            payload.value = serialize();
            return true;
        }

        if (toolbar) {
            toolbar.addEventListener("mousedown", function (event) {
                // Keep the selection while the button is pressed.
                event.preventDefault();
            });
            toolbar.addEventListener("click", function (event) {
                var btn = event.target.closest("button");
                if (!btn) return;
                if (btn.hasAttribute("data-cmd")) {
                    exec(btn.getAttribute("data-cmd"));
                } else if (btn.hasAttribute("data-block")) {
                    applyBlock(btn.getAttribute("data-block"));
                }
            });
        }

        surface.addEventListener("input", sync);
        surface.addEventListener("keyup", sync);
        surface.addEventListener("mouseup", sync);
        surface.addEventListener("focus", sync);
        surface.addEventListener("blur", rememberSelection);
        surface.addEventListener("paste", function (event) {
            var clipboard = event.clipboardData;
            if (!clipboard) return;
            var html = clipboard.getData("text/html");
            if (!html) return;
            // Paste as sanitized plain text: pasted markup would otherwise
            // smuggle styles the server-side whitelist would strip anyway.
            event.preventDefault();
            var text = clipboard.getData("text/plain");
            document.execCommand("insertText", false, text);
            sync();
        });

        surface.addEventListener("keydown", function (event) {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
                event.preventDefault();
                if (!collectContent()) return;
                form.requestSubmit ? form.requestSubmit() : form.submit();
            }
        });

        if (revertBtn) {
            revertBtn.addEventListener("click", function () {
                surface.innerHTML = original;
                sync();
                surface.focus();
            });
        }

        form.addEventListener("submit", function (event) {
            if (!collectContent()) {
                event.preventDefault();
                return;
            }
            original = serialize();
            setDirty(false);
        });

        window.addEventListener("beforeunload", function (event) {
            if (serialize() === original) return;
            event.preventDefault();
            event.returnValue = "";
        });

        sync();
    }

    function boot() {
        document.querySelectorAll("[data-editor-form]").forEach(initEditor);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();