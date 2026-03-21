"use strict";

document.addEventListener("DOMContentLoaded", async () => {
    const serverUrlInput = document.getElementById("server-url");
    const apiKeyInput = document.getElementById("api-key");
    const defaultTagsInput = document.getElementById("default-tags");
    const autoSummarizeCheckbox = document.getElementById("auto-summarize");
    const saveBtn = document.getElementById("save-btn");
    const testBtn = document.getElementById("test-btn");
    const statusEl = document.getElementById("status");

    // Load saved settings
    const settings = await chrome.storage.sync.get([
        "serverUrl",
        "apiKey",
        "defaultTags",
        "autoSummarize",
    ]);

    serverUrlInput.value = settings.serverUrl || "";
    apiKeyInput.value = settings.apiKey || "";
    defaultTagsInput.value = settings.defaultTags || "";
    autoSummarizeCheckbox.checked = settings.autoSummarize || false;

    // Save settings
    saveBtn.addEventListener("click", async () => {
        const serverUrl = serverUrlInput.value.trim();
        const apiKey = apiKeyInput.value.trim();

        if (!serverUrl) {
            showStatus("Server URL is required.", "error");
            return;
        }
        if (!apiKey) {
            showStatus("API Key is required.", "error");
            return;
        }

        await chrome.storage.sync.set({
            serverUrl,
            apiKey,
            defaultTags: defaultTagsInput.value.trim(),
            autoSummarize: autoSummarizeCheckbox.checked,
        });

        showStatus("Settings saved.", "success");
    });

    // Test connection
    testBtn.addEventListener("click", async () => {
        const serverUrl = serverUrlInput.value.trim();
        const apiKey = apiKeyInput.value.trim();

        if (!serverUrl || !apiKey) {
            showStatus("Fill in Server URL and API Key first.", "error");
            return;
        }

        testBtn.disabled = true;
        testBtn.textContent = "Testing...";

        try {
            const endpoint = `${serverUrl.replace(/\/+$/, "")}/v1/tags`;
            const response = await fetch(endpoint, {
                headers: { Authorization: `Bearer ${apiKey}` },
            });

            if (response.ok) {
                showStatus("Connection successful!", "success");
            } else {
                showStatus(`Connection failed: HTTP ${response.status}`, "error");
            }
        } catch (err) {
            showStatus(`Connection failed: ${err.message}`, "error");
        } finally {
            testBtn.disabled = false;
            testBtn.textContent = "Test Connection";
        }
    });

    function showStatus(text, type) {
        statusEl.textContent = text;
        statusEl.className = `status ${type}`;
        statusEl.hidden = false;
    }
});
