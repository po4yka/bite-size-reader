"use strict";

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg.type === "getSelection") {
        sendResponse({ text: window.getSelection()?.toString() || "" });
    }
});
