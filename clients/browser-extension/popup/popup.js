"use strict";

const MAX_DISPLAY_TAGS = 8;
const MAX_RECENT_DISPLAY = 5;

document.addEventListener("DOMContentLoaded", async () => {
    const titleInput = document.getElementById("page-title");
    const urlInput = document.getElementById("page-url");
    const tagChips = document.getElementById("tag-chips");
    const tagInput = document.getElementById("tag-input");
    const summarizeCheckbox = document.getElementById("summarize-checkbox");
    const saveBtn = document.getElementById("save-btn");
    const statusMsg = document.getElementById("status-msg");
    const recentList = document.getElementById("recent-list");
    const noRecent = document.getElementById("no-recent");
    const notConfigured = document.getElementById("not-configured");
    const openOptions = document.getElementById("open-options");
    const saveSection = document.getElementById("save-section");

    const selectedTags = new Set();

    // Open options page link
    openOptions.addEventListener("click", (e) => {
        e.preventDefault();
        chrome.runtime.openOptionsPage();
    });

    // Check configuration
    const settings = await chrome.storage.sync.get(["serverUrl", "apiKey", "autoSummarize"]);
    if (!settings.serverUrl || !settings.apiKey) {
        saveSection.hidden = true;
        notConfigured.hidden = false;
        await loadRecentSaves();
        return;
    }

    // Auto-summarize default
    summarizeCheckbox.checked = settings.autoSummarize || false;

    // Fill current tab info
    try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab) {
            titleInput.value = tab.title || "";
            urlInput.value = tab.url || "";
        }
    } catch (err) {
        console.error("Failed to get active tab:", err);
    }

    // Fetch tags from server
    await fetchAndRenderTags(settings.serverUrl, settings.apiKey, tagChips, selectedTags);

    // Custom tag input
    tagInput.addEventListener("keydown", (e) => {
        if (e.key !== "Enter") return;
        e.preventDefault();
        const tag = tagInput.value.trim();
        if (!tag) return;
        tagInput.value = "";

        if (selectedTags.has(tag)) return;
        selectedTags.add(tag);
        appendTagChip(tagChips, tag, selectedTags, true);
    });

    // Save button
    saveBtn.addEventListener("click", async () => {
        saveBtn.disabled = true;
        saveBtn.textContent = "Saving...";
        hideStatus();

        try {
            const response = await chrome.runtime.sendMessage({
                type: "saveToReader",
                url: urlInput.value,
                title: titleInput.value,
                selectedText: "",
                tags: [...selectedTags],
                summarize: summarizeCheckbox.checked,
            });

            if (response?.ok) {
                showStatus("Saved successfully!", "success");
            } else {
                showStatus(response?.error || "Save failed.", "error");
            }
        } catch (err) {
            showStatus(err.message || "Save failed.", "error");
        } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = "Save";
            await loadRecentSaves();
        }
    });

    // Load recent saves
    await loadRecentSaves();

    // -- Helper functions --

    function showStatus(text, type) {
        statusMsg.textContent = text;
        statusMsg.className = `status-msg ${type}`;
        statusMsg.hidden = false;
    }

    function hideStatus() {
        statusMsg.hidden = true;
    }

    async function loadRecentSaves() {
        const { recentSaves = [] } = await chrome.storage.local.get("recentSaves");
        recentList.innerHTML = "";

        const toShow = recentSaves.slice(0, MAX_RECENT_DISPLAY);
        if (toShow.length === 0) {
            noRecent.hidden = false;
            return;
        }

        noRecent.hidden = true;
        for (const save of toShow) {
            const li = document.createElement("li");
            const a = document.createElement("a");
            a.href = save.url;
            a.textContent = save.title || save.url;
            a.title = save.url;
            a.target = "_blank";
            a.rel = "noopener";

            const time = document.createElement("span");
            time.className = "save-time";
            time.textContent = formatRelativeTime(save.savedAt);

            li.appendChild(a);
            li.appendChild(time);
            recentList.appendChild(li);
        }
    }
});

async function fetchAndRenderTags(serverUrl, apiKey, container, selectedTags) {
    try {
        const endpoint = `${serverUrl.replace(/\/+$/, "")}/v1/tags`;
        const response = await fetch(endpoint, {
            headers: { Authorization: `Bearer ${apiKey}` },
        });

        if (!response.ok) return;

        const data = await response.json();
        const tags = Array.isArray(data) ? data : data.tags || [];

        const topTags = tags.slice(0, MAX_DISPLAY_TAGS);
        for (const tag of topTags) {
            const tagName = typeof tag === "string" ? tag : tag.name || tag.tag || "";
            if (!tagName) continue;
            appendTagChip(container, tagName, selectedTags, false);
        }
    } catch (err) {
        console.error("Failed to fetch tags:", err);
    }
}

function appendTagChip(container, tagName, selectedTags, isActive) {
    const chip = document.createElement("span");
    chip.className = `tag-chip${isActive ? " active" : ""}`;
    chip.textContent = tagName;
    chip.addEventListener("click", () => {
        chip.classList.toggle("active");
        if (chip.classList.contains("active")) {
            selectedTags.add(tagName);
        } else {
            selectedTags.delete(tagName);
        }
    });
    container.appendChild(chip);
}

function formatRelativeTime(timestamp) {
    if (!timestamp) return "";
    const seconds = Math.floor((Date.now() - timestamp) / 1000);
    if (seconds < 60) return "just now";
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
}
