# Bite-Size Reader Browser Extension

## Development Setup

### Chrome

1. Open `chrome://extensions/`
2. Enable "Developer mode" (top right toggle)
3. Click "Load unpacked"
4. Select this `extension/` directory
5. The extension icon appears in the toolbar

### Firefox

1. Open `about:debugging#/runtime/this-firefox`
2. Click "Load Temporary Add-on"
3. Select `extension/manifest.json`

### Configuration

1. Click the extension icon -> "Settings" (or right-click -> Options)
2. Enter your BSR server URL (e.g., `https://bsr.example.com`)
3. Enter your API key (from BSR Settings -> API Keys)
4. Click "Test Connection" to verify
5. Click "Save"

## Usage

- Click extension icon to save current page
- Use Ctrl+Shift+S (Cmd+Shift+S on Mac) for quick save
- Right-click on page -> "Save to Bite-Size Reader"
- Right-click on selected text -> "Save selection to Bite-Size Reader"

## Icons

Place PNG icon files in the `icons/` directory:

- `icon-16.png` (16x16)
- `icon-48.png` (48x48)
- `icon-128.png` (128x128)

## Project Structure

```
extension/
  background/       Service worker for background tasks
  content/          Content script injected into pages
  icons/            Extension icons
  options/          Settings/options page
  popup/            Popup UI when clicking the extension icon
  manifest.json     Extension manifest (Manifest V3)
```
