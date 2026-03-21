# Browser Extension

**Status:** Missing
**Complexity:** Medium
**Dependencies:** Quick-save API endpoint, User Tags ([01-user-tags.md](01-user-tags.md))

## Problem Statement

BSR's only entry points are Telegram (send URL to bot) and the web frontend (submit page). There is no way to save a page directly from the browser while reading. Karakeep provides Chrome and Firefox extensions with one-click save, keyboard shortcuts, and tag assignment.

## Design Goals

- One-click save of the current page URL to BSR
- Optional: select text to include as a note
- Quick tag assignment from existing user tags
- Minimal UI -- popup with save status and recent saves
- Manifest V3 (Chrome) / WebExtension API (Firefox)
- Auth via API key (from BSR's existing `ClientSecret` model)

## Extension Architecture

```
extension/
  manifest.json          # Manifest V3
  background/
    service-worker.js    # API calls, badge updates
  popup/
    popup.html           # Popup UI
    popup.js             # Popup logic
    popup.css            # Styles
  options/
    options.html         # Settings page
    options.js           # Settings logic
  content/
    content-script.js    # Text selection (optional)
  icons/
    icon-16.png
    icon-48.png
    icon-128.png
```

### Technology Choice

Vanilla HTML/JS/CSS for the extension UI. Rationale:

- Extension popup is tiny (one form, one list) -- React is overkill
- Smaller bundle size = faster popup open
- No build step required for development
- Easier cross-browser compatibility

If the extension grows significantly, migrate to a lightweight framework (Preact/Svelte).

## Backend API

### New Endpoint

Add to `app/api/routers/requests.py` or create `app/api/routers/quick_save.py`:

```
POST /v1/quick-save
```

**Request Body:**

```json
{
    "url": "https://example.com/article",
    "title": "Article Title",
    "selected_text": "Optional highlighted text from the page",
    "tag_names": ["research", "ai"],
    "summarize": true
}
```

**Response:**

```json
{
    "request_id": "abc-123",
    "status": "pending",
    "title": "Article Title",
    "url": "https://example.com/article",
    "tags_attached": ["research", "ai"],
    "duplicate": false
}
```

If the URL already exists (duplicate `dedupe_hash`), return the existing summary:

```json
{
    "request_id": "existing-456",
    "status": "completed",
    "title": "Article Title",
    "url": "https://example.com/article",
    "duplicate": true,
    "summary_id": "sum-789"
}
```

**Behavior:**

1. Normalize URL, compute `dedupe_hash`
2. If duplicate: return existing request/summary
3. If new: create `Request` (type="extension"), attach tags, optionally enqueue for summarization
4. Return immediately (async processing)

### Auth

Uses existing `ClientSecret`-based auth with Bearer token:

```
Authorization: Bearer {client_id}:{client_secret}
```

The extension settings page stores the BSR server URL and API credentials.

## Extension Features

### 1. Popup (Main UI)

When clicked, the popup shows:

```
+---------------------------+
|  Bite-Size Reader         |
+---------------------------+
|  [Title of current page]  |
|  URL: example.com/...     |
|                           |
|  Tags: [research] [+]     |
|                           |
|  [x] Summarize            |
|                           |
|  [ Save to BSR ]          |
+---------------------------+
|  Recent saves:            |
|  - Article A  (2m ago)    |
|  - Article B  (1h ago)    |
+---------------------------+
```

- Auto-fills title and URL from active tab
- Tag picker: shows 8 most-used tags as toggleable chips, plus a text input for new tags
- "Summarize" checkbox (default from user preferences)
- Save button triggers `POST /v1/quick-save`
- Recent saves section shows last 5 saved items (cached in extension storage)

### 2. Keyboard Shortcut

`Ctrl+Shift+S` (configurable) -- saves current page with default tags and summarize settings. No popup interaction needed.

### 3. Context Menu

Right-click on page: "Save to Bite-Size Reader"
Right-click on selected text: "Save selection to Bite-Size Reader" (saves URL + selected text as note)

### 4. Badge

After saving, show a checkmark badge on the extension icon for 3 seconds. If the current page is already saved, show a dot indicator.

### 5. Options Page

```
+---------------------------+
|  Settings                 |
+---------------------------+
|  Server URL:              |
|  [https://bsr.example.com]|
|                           |
|  API Key:                 |
|  [client_id:secret]       |
|                           |
|  [ Test Connection ]      |
|                           |
|  Default tags:            |
|  [tag1, tag2]             |
|                           |
|  Auto-summarize: [x]      |
|                           |
|  Keyboard shortcut:       |
|  [Ctrl+Shift+S]           |
+---------------------------+
```

## Manifest V3

```json
{
    "manifest_version": 3,
    "name": "Bite-Size Reader",
    "version": "1.0.0",
    "description": "Save and summarize web pages with Bite-Size Reader",
    "permissions": [
        "activeTab",
        "storage",
        "contextMenus"
    ],
    "host_permissions": [
        "<all_urls>"
    ],
    "action": {
        "default_popup": "popup/popup.html",
        "default_icon": {
            "16": "icons/icon-16.png",
            "48": "icons/icon-48.png",
            "128": "icons/icon-128.png"
        }
    },
    "background": {
        "service_worker": "background/service-worker.js"
    },
    "content_scripts": [
        {
            "matches": ["<all_urls>"],
            "js": ["content/content-script.js"],
            "run_at": "document_idle"
        }
    ],
    "options_page": "options/options.html",
    "commands": {
        "quick-save": {
            "suggested_key": {
                "default": "Ctrl+Shift+S",
                "mac": "Command+Shift+S"
            },
            "description": "Save current page to Bite-Size Reader"
        }
    }
}
```

## Content Script

The content script is minimal -- it only activates when the user selects text and right-clicks:

```javascript
// content/content-script.js
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === "getSelection") {
        sendResponse({ text: window.getSelection()?.toString() || "" });
    }
});
```

## Cross-Browser Compatibility

### Chrome

- Manifest V3 with service worker
- Publish to Chrome Web Store

### Firefox

- Same codebase works with WebExtension API
- Replace `chrome.*` with `browser.*` (or use polyfill)
- Publish to Firefox Add-ons (AMO)

Use [webextension-polyfill](https://github.com/nicolo-ribaudo/webextension-polyfill) for API compatibility.

## Project Location

Two options:

**Option A (recommended):** Separate directory in BSR repo: `extension/`

- Pros: co-located with API, shared versioning
- Cons: different tech stack in same repo

**Option B:** Separate repository

- Pros: independent release cycle
- Cons: API contract drift

Recommend Option A for simplicity.

## Telegram Equivalent

Note that Telegram's "share" functionality already serves as a mobile equivalent of the browser extension:

- Share URL to BSR bot -> same effect as extension save
- Forward messages -> summarize channel content

The browser extension targets desktop browsing where Telegram is not the primary interface.

## Testing

- Manual testing: install unpacked extension, save pages, verify API calls
- API integration test: call `POST /v1/quick-save` with various payloads
- Duplicate detection test: save same URL twice, verify duplicate response
- Options page test: configure server URL, verify connection test works
