/**
 * Bootstraps the embedded ONLYOFFICE editor for a learning material.
 *
 * The page asks Django for a signed editor config (ONLYOFFICE requires a JWT),
 * loads the Document Server's api.js, and mounts the viewer. If anything fails
 * the built-in HTML editor underneath becomes visible instead, so the page is
 * never a dead end.
 */
(function () {
    "use strict";

    function ready(fn) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", fn);
        } else {
            fn();
        }
    }

    function fallback(root, message) {
        var editor = document.querySelector("[data-editor-form]");
        if (editor) editor.removeAttribute("hidden");
        if (message && window.showToast) window.showToast(message, "warning");
        root.innerHTML = "";
    }

    function loadScript(src) {
        return new Promise(function (resolve, reject) {
            var script = document.createElement("script");
            script.src = src;
            script.async = true;
            script.onload = resolve;
            script.onerror = function () {
                reject(new Error("Could not load the document editor."));
            };
            document.head.appendChild(script);
        });
    }

    function csrfToken() {
        var input = document.querySelector("[name=csrfmiddlewaretoken]");
        return input ? input.value : "";
    }

    function initOffice(root) {
        var configUrl = root.getAttribute("data-office-config-url");
        if (!configUrl) return;

        fetch(configUrl, {
            method: "POST",
            headers: {
                Accept: "application/json",
                "X-CSRFToken": csrfToken(),
            },
            credentials: "same-origin",
        })
            .then(function (response) {
                if (!response.ok) throw new Error("Editor config failed.");
                return response.json();
            })
            .then(function (data) {
                if (!data || !data.enabled || !data.config) {
                    throw new Error((data && data.error) || "Editor unavailable.");
                }
                return loadScript(data.api_url).then(function () {
                    return data;
                });
            })
            .then(function (data) {
                if (!window.DocsAPI || !window.DocsAPI.DocEditor) {
                    throw new Error("Document editor did not initialise.");
                }
                root.innerHTML = '<div id="onlyoffice-editor" style="height:100%"></div>';
                data.config.events = {
                    /* Mirrors the editor's real state into the header indicator. */
                    onDocumentStateChange: function (event) {
                        document.dispatchEvent(
                            new CustomEvent("materials:savestate", {
                                detail: { state: event.data === false ? "saved" : "dirty" },
                            })
                        );
                    },
                };
                /* eslint-disable no-new */
                new window.DocsAPI.DocEditor("onlyoffice-editor", data.config);
            })
            .catch(function (err) {
                fallback(root, (err && err.message) || "Document editor unavailable.");
            });
    }

    ready(function () {
        document.querySelectorAll("[data-office-root]").forEach(initOffice);
    });
})();