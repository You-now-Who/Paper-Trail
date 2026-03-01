/**
 * background.js — Service worker: relays fetch to backend when content script requests.
 * Open chrome://extensions → Paper Trail → "Inspect views: service worker" for logs.
 */

const DEBUG = true;
const BACKEND = 'http://127.0.0.1:8080';
const LOG = (...args) => DEBUG && console.log('[PaperTrail BG]', ...args);

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === 'REPORT') {
    LOG('REPORT request');
    fetch(`${BACKEND}/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(msg.payload || {}),
    })
      .then((r) => {
        if (!r.ok) return Promise.reject(new Error(r.status + ' ' + r.statusText));
        return r.text();
      })
      .then((html) => {
        const base64 = btoa(unescape(encodeURIComponent(html)));
        const dataUrl = 'data:text/html;base64,' + base64;
        chrome.tabs.create({ url: dataUrl });
        sendResponse({ ok: true });
      })
      .catch((e) => {
        LOG('REPORT error', e.message);
        sendResponse({ error: String(e.message) });
      });
    return true;
  }
  if (msg.type === 'TRACE') {
    LOG('TRACE request', msg.payload?.text?.slice(0, 50));
    fetch(`${BACKEND}/trace`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(msg.payload),
    })
      .then((r) => {
        if (!r.ok) {
          LOG('TRACE HTTP error', r.status, r.statusText);
          return Promise.reject(new Error(r.status + ' ' + r.statusText));
        }
        return r.json();
      })
      .then((data) => { LOG('TRACE success'); sendResponse(data); })
      .catch((e) => { LOG('TRACE error', e.message); sendResponse({ error: String(e.message || e) }); });
    return true; // async response
  }
  if (msg.type === 'HEALTH') {
    LOG('HEALTH check');
    fetch(`${BACKEND}/health`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then(sendResponse)
      .catch((e) => sendResponse({ error: String(e.message || e) }));
    return true;
  }
});
