/**
 * content.js — DOM injection, Trace button, inline panel.
 * Set DEBUG = true for console logs only (no debug panel).
 */

(function () {
  'use strict';
  const BACKEND = 'http://127.0.0.1:8080';

  function createTraceButton() {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'pt-trace-btn';
    btn.setAttribute('aria-label', 'Trace provenance');
    btn.textContent = 'Trace';
    return btn;
  }

  function findPostActionsBars() {
    // Bluesky: replyBtn/repostBtn/likeBtn live in a parent div — use its parent as the bar
    var replyBtns = document.querySelectorAll('[data-testid="replyBtn"]');
    if (replyBtns.length > 0) {
      var bars = [];
      replyBtns.forEach(function (btn) {
        var bar = btn.closest('[role="group"]') || btn.parentElement;
        if (bar && !bar.querySelector('.pt-trace-btn')) bars.push(bar);
      });
      if (bars.length > 0) return bars;
    }
    // Bluesky fallback: use engagement area inside feedItem
    var feedItems = document.querySelectorAll('[data-testid^="feedItem-by-"]');
    if (feedItems.length > 0) {
      var bars = [];
      feedItems.forEach(function (item) {
        var replyEl = item.querySelector('[data-testid="replyBtn"]');
        var bar = replyEl ? (replyEl.closest('[role="group"]') || replyEl.parentElement) : item.querySelector('[role="group"]');
        if (bar && !bar.querySelector('.pt-trace-btn')) bars.push(bar);
      });
      if (bars.length > 0) return bars;
    }
    const selectors = [
      '[data-testid="postActions"]',
      '[data-testid="post-actions"]',
      'article [role="group"]',
      '[role="article"] [role="group"]',
      'div[role="group"]',
    ];
    for (var i = 0; i < selectors.length; i++) {
      var els = document.querySelectorAll(selectors[i]);
      var filtered = Array.from(els).filter(function (g) {
        if (g.querySelector('.pt-trace-btn')) return false;
        var btns = g.querySelectorAll('button, a[role="button"], [role="button"]');
        return btns.length >= 1;
      });
      if (filtered.length > 0) return filtered;
    }
    var posts = document.querySelectorAll('article, [role="article"], [data-testid="post"]');
    var bars = [];
    posts.forEach(function (p) {
      if (p.querySelector('.pt-trace-btn')) return;
      var footer = p.querySelector('footer, [role="group"], div:last-child');
      if (footer && !footer.querySelector('.pt-trace-btn')) bars.push(footer);
    });
    return bars;
  }

  function getPostData(button) {
    const root = button.closest('[data-testid^="feedItem-by-"]') || button.closest('article') || button.closest('[data-testid="post"]') || button.closest('[role="article"]');
    if (!root) return null;
    const textEl = root.querySelector('[data-testid="postText"]') || root.querySelector('[dir="auto"]') || root.querySelector('p');
    const text = textEl ? (textEl.textContent || '').trim() : '';
    const timeEl = root.querySelector('time[datetime]');
    const timestamp = timeEl ? (timeEl.getAttribute('datetime') || '').trim() : '';
    const authorEl = root.querySelector('a[href*="/profile/"]');
    let author = '';
    if (authorEl) {
      const m = (authorEl.getAttribute('href') || '').match(/\/profile\/([^/]+)/);
      author = m ? m[1] : (authorEl.textContent || '').trim();
    }
    const postLink = root.querySelector('a[href*="/profile/"][href*="/post/"]');
    const url = postLink && postLink.href ? postLink.href : window.location.href;
    return { text: text, timestamp: timestamp, author: author, url: url };
  }

  function escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  function injectTraceButtons() {
    try {
      const bars = findPostActionsBars();
      if (bars.length === 0) {
        console.log('[PaperTrail] No action bars found — Bluesky DOM may have changed. Right‑click a post → Inspect to see structure.');
      }
      bars.forEach(function (bar) {
        if (bar.querySelector('.pt-trace-btn')) return;
        const btn = createTraceButton();
        bar.appendChild(btn);
        btn.addEventListener('click', function (e) {
          e.preventDefault();
          e.stopPropagation();
          onTraceClick(btn, bar);
        });
      });
    } catch (err) {
      console.error('[PaperTrail] injectTraceButtons error', err);
    }
  }

  function onTraceClick(button, actionBar) {
    console.log('[PaperTrail] Trace clicked');
    const data = getPostData(button);
    if (!data || !data.text) {
      console.warn('[PaperTrail] No post text found', data);
      showPanel(actionBar, { error: 'Could not read post text. Open F12 console for details.' });
      return;
    }
    const anchor = actionBar.closest('[data-testid^="feedItem-by-"]') || actionBar.closest('article') || actionBar.closest('section') || actionBar;
    const existing = anchor && anchor.nextElementSibling && anchor.nextElementSibling.classList.contains('pt-panel');
    if (existing) anchor.nextElementSibling.remove();
    const loading = document.createElement('div');
    loading.className = 'pt-panel pt-loading';
    loading.textContent = 'Tracing…';
    if (anchor) anchor.after(loading);

    chrome.runtime.sendMessage({ type: 'TRACE', payload: data }, function (response) {
      loading.remove();
      const insertAfter = anchor || actionBar;
      if (chrome.runtime.lastError) {
        console.error('[PaperTrail] Extension error:', chrome.runtime.lastError.message);
        showPanel(insertAfter, { error: 'Extension error: ' + (chrome.runtime.lastError.message || 'unknown') });
        return;
      }
      if (response && response.error) {
        console.error('[PaperTrail] Backend error:', response.error);
        showPanel(insertAfter, { error: response.error });
        return;
      }
      console.log('[PaperTrail] Got response', response ? 'ok' : 'empty');
      showPanel(insertAfter, response || {});
    });
  }

  function showPanel(insertAfter, data) {
    if (!insertAfter) return;
    const existing = insertAfter.nextElementSibling;
    if (existing && existing.classList.contains('pt-panel')) existing.remove();
    const panel = document.createElement('div');
    panel.className = 'pt-panel';
    if (data && data.error) {
      panel.innerHTML = '<div class="pt-error">' + escapeHtml(data.error) + '</div>';
    } else {
      panel.appendChild(renderProvenance(data || {}));
    }
    insertAfter.after(panel);
  }

  function renderProvenance(res) {
    const wrap = document.createElement('div');
    wrap.className = 'pt-provenance';

    const us = res.user_summary || {};
    const oneLiner = us.one_liner || 'No result.';
    const confidence = (us.confidence || 'medium').toLowerCase();
    const confClass = 'pt-confidence pt-' + confidence;

    wrap.innerHTML =
      '<div class="pt-card-header">' +
      '<div class="pt-summary">' +
      '<div class="pt-one-liner">' + escapeHtml(oneLiner) + '</div>' +
      '<span class="' + confClass + '" aria-label="Confidence: ' + escapeHtml(confidence) + '">' + escapeHtml(confidence) + '</span>' +
      '</div>' +
      '<button type="button" class="pt-report-btn" aria-label="View full report">View report</button>' +
      '</div>';

    const reportBtn = wrap.querySelector('.pt-report-btn');
    reportBtn.addEventListener('click', function () {
      chrome.runtime.sendMessage({ type: 'REPORT', payload: res }, function (r) {
        if (r && r.error) console.error('[PaperTrail] Report error:', r.error);
      });
    });

    // Optional "Show more" to expand full provenance
    const hasMore = res.origin && (res.timeline && res.timeline.length || res.diff && (res.diff.removed && res.diff.removed.length || res.diff.added && res.diff.added.length) || res.reply_draft);
    if (hasMore && us.show_more) {
      const moreBtn = document.createElement('button');
      moreBtn.type = 'button';
      moreBtn.className = 'pt-more-btn';
      moreBtn.textContent = 'Show details';
      wrap.appendChild(moreBtn);
      const details = document.createElement('div');
      details.className = 'pt-details';
      details.style.display = 'none';

      const origin = res.origin || {};
      details.innerHTML =
        '<div class="pt-card pt-origin"><div class="pt-card-title">Origin</div>' +
        '<div class="pt-meta">' + escapeHtml(origin.source || '') + ' · ' + escapeHtml(origin.community || '') + '</div>' +
        '<div class="pt-text">' + escapeHtml((origin.text || '').slice(0, 300)) + ((origin.text || '').length > 300 ? '…' : '') + '</div></div>';

      if (res.diff && (res.diff.removed && res.diff.removed.length || res.diff.added && res.diff.added.length)) {
        let d = '<div class="pt-diff"><div class="pt-card-title">Diff</div><div class="pt-diff-list">';
        (res.diff.removed || []).forEach(function (p) { d += '<span class="pt-removed">− ' + escapeHtml(p) + '</span>'; });
        (res.diff.added || []).forEach(function (p) { d += '<span class="pt-added">+ ' + escapeHtml(p) + '</span>'; });
        d += '</div></div>';
        details.innerHTML += d;
      }
      if (res.reply_draft) {
        details.innerHTML += '<div class="pt-reply"><div class="pt-card-title">Reply draft</div><div class="pt-reply-text">' + escapeHtml(res.reply_draft) + '</div><button type="button" class="pt-copy-btn">Copy reply</button></div>';
      }

      wrap.appendChild(details);
      moreBtn.addEventListener('click', function () {
        const show = details.style.display === 'none';
        details.style.display = show ? 'block' : 'none';
        moreBtn.textContent = show ? 'Hide details' : 'Show details';
      });

      const copyBtn = details.querySelector('.pt-copy-btn');
      if (copyBtn) copyBtn.addEventListener('click', function () {
        navigator.clipboard.writeText(res.reply_draft).then(function () {
          copyBtn.textContent = 'Copied';
          setTimeout(function () { copyBtn.textContent = 'Copy reply'; }, 2000);
        });
      });
    }
    return wrap;
  }

  // Debounce MutationObserver so we don't fire on every tiny DOM change
  let debounceTimer = null;
  function debouncedInject() {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () {
      debounceTimer = null;
      injectTraceButtons();
    }, 300);
  }

  try {
    console.log('[PaperTrail] Script loaded on', window.location.href);
    function run() {
      injectTraceButtons();
      const target = document.body || document.documentElement;
      if (target) {
        const observer = new MutationObserver(debouncedInject);
        observer.observe(target, { childList: true, subtree: true });
      }
    }
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', run);
    } else {
      run();
    }
  } catch (err) {
    console.error('[PaperTrail] init error', err);
  }
})();
