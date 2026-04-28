"use strict";

const CONTEXT_MENU_SAVE_PAGE = "ratatoskr-save-page";
const CONTEXT_MENU_SAVE_SELECTION = "ratatoskr-save-selection";
const BADGE_CLEAR_DELAY_MS = 3000;
const MAX_RECENT_SAVES = 20;

chrome.runtime.onInstalled.addListener(() => {
    chrome.contextMenus.create({
        id: CONTEXT_MENU_SAVE_PAGE,
        title: "Save to Ratatoskr",
        contexts: ["page", "link"],
    });

    chrome.contextMenus.create({
        id: CONTEXT_MENU_SAVE_SELECTION,
        title: "Save selection to Ratatoskr",
        contexts: ["selection"],
    });
});

chrome.commands.onCommand.addListener(async (command) => {
    if (command !== "quick-save") return;

    try {
        const [tab] = await chrome.tabs.query({
            active: true,
            currentWindow: true,
        });
        if (!tab) return;

        const selection = await getSelectionFromTab(tab.id);
        await saveToReader(tab.url, tab.title, selection, []);
    } catch (err) {
        console.error("quick-save failed:", err);
        setBadge("X", "#e74c3c");
    }
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
    try {
        const url = info.linkUrl || info.pageUrl || tab?.url || "";
        const title = tab?.title || "";
        const selectedText =
            info.menuItemId === CONTEXT_MENU_SAVE_SELECTION
                ? info.selectionText || ""
                : "";

        await saveToReader(url, title, selectedText, []);
    } catch (err) {
        console.error("context-menu save failed:", err);
        setBadge("X", "#e74c3c");
    }
});

// Listen for messages from popup
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg.type === "saveToReader") {
        saveToReader(msg.url, msg.title, msg.selectedText, msg.tags, msg.summarize)
            .then((result) => sendResponse({ ok: true, data: result }))
            .catch((err) => sendResponse({ ok: false, error: err.message }));
        return true; // keep channel open for async response
    }
});

/**
 * Save a page/selection to the Ratatoskr API.
 */
async function saveToReader(url, title, selectedText = "", tags = [], summarize = false) {
    const settings = await chrome.storage.sync.get([
        "serverUrl",
        "apiKey",
        "defaultTags",
        "autoSummarize",
    ]);

    const serverUrl = settings.serverUrl;
    const apiKey = settings.apiKey;

    if (!serverUrl || !apiKey) {
        setBadge("!", "#f39c12");
        throw new Error("Server URL or API Key not configured. Open extension options.");
    }

    const allTags = [
        ...tags,
        ...(settings.defaultTags ? settings.defaultTags.split(",").map((t) => t.trim()).filter(Boolean) : []),
    ];

    const shouldSummarize = summarize ?? settings.autoSummarize ?? false;

    const body = {
        url,
        title,
        tags: [...new Set(allTags)],
    };

    if (selectedText) {
        body.selected_text = selectedText;
    }
    if (shouldSummarize) {
        body.summarize = true;
    }

    const endpoint = `${serverUrl.replace(/\/+$/, "")}/v1/quick-save`;

    const response = await fetch(endpoint, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify(body),
    });

    if (!response.ok) {
        const text = await response.text().catch(() => "");
        throw new Error(`API error ${response.status}: ${text}`);
    }

    const data = await response.json();

    // Success badge
    setBadge("OK", "#27ae60");

    // Store in recent saves
    await addRecentSave({ url, title, tags: allTags, savedAt: Date.now() });

    return data;
}

/**
 * Get selected text from a tab's content script.
 */
async function getSelectionFromTab(tabId) {
    try {
        const response = await chrome.tabs.sendMessage(tabId, {
            type: "getSelection",
        });
        return response?.text || "";
    } catch {
        return "";
    }
}

/**
 * Set the extension badge text and color, clearing after a delay.
 */
function setBadge(text, color) {
    chrome.action.setBadgeText({ text });
    chrome.action.setBadgeBackgroundColor({ color });
    setTimeout(() => {
        chrome.action.setBadgeText({ text: "" });
    }, BADGE_CLEAR_DELAY_MS);
}

/**
 * Append a save entry to recent saves in local storage.
 */
async function addRecentSave(entry) {
    const { recentSaves = [] } = await chrome.storage.local.get("recentSaves");
    recentSaves.unshift(entry);
    if (recentSaves.length > MAX_RECENT_SAVES) {
        recentSaves.length = MAX_RECENT_SAVES;
    }
    await chrome.storage.local.set({ recentSaves });
}
