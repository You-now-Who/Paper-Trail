# Debugging the Paper Trail Extension

## 1. Confirm content script loads

- Go to **bsky.app** (or your Bluesky URL)
- Press **F12** to open DevTools
- Go to **Console**
- Look for `[PaperTrail] content.js loaded` — if you don't see it, the content script is not running

**If content script doesn't load:**
- Check `chrome://extensions/` → Paper Trail → "Errors" or "Details"
- Confirm the extension is enabled
- Confirm you're on `https://bsky.app/*` or `https://*.bsky.app/*`
- Try refreshing the page (Ctrl+Shift+R)
- Click "Reload" on the extension card in `chrome://extensions/`

## 2. Confirm debug panel

- A **green debug panel** should appear at the bottom-right when the content script runs
- It logs: "content.js loaded", "findPostActionsBars", "injectTraceButtons", etc.
- If you see the panel but no buttons, DOM selectors are likely wrong for this Bluesky layout

## 3. Inspect Bluesky DOM

- Right-click a post → **Inspect**
- In DevTools Elements, inspect the post container (often `article`, `[role="article"]`)
- Find the action bar (Like, Repost, Reply buttons)
- Note the selector (e.g. `[data-testid="postActions"]` or `[role="group"]`)
- Share that structure so selectors in `content.js` can be updated

## 4. Background / backend logs

- `chrome://extensions/` → Paper Trail → **"Inspect views: service worker"**
- A DevTools window opens for the background script
- Console shows `[PaperTrail BG] TRACE request`, `TRACE success`, or `TRACE error`
- If you see `TRACE error` or network errors, check that the backend is running on `http://127.0.0.1:8000`

## 5. Turn off debug panel

- Edit `content.js`, set `const DEBUG = false;` at the top
- Reload the extension
