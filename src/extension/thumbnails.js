'use strict';

/**
 * DeArrow thumbnails for YouTube on TV.
 *
 * Leanback paints each thumbnail as the CSS background of a
 * ytlr-thumbnail-details element, and its Content Security Policy only lets
 * the page load images from Google. Images requested from an extension's
 * isolated world are checked against the extension's policy instead, so this
 * script lays the DeArrow image over YouTube's thumbnail as an <img> once the
 * image has loaded. YouTube's policy stays exactly as sent, and a thumbnail
 * DeArrow cannot deliver leaves YouTube's in place.
 */
(() => {
  const THUMBNAIL = 'ytlr-thumbnail-details';
  const OVERLAY = 'steamos-yt-dearrow';
  const VIDEO_IN_URL = /\/vi(?:_webp)?\/([\w-]{11})\//;
  const BATCH_MS = 40;
  const RETRY_MS = 5000;
  const ATTEMPTS = 3;
  const KNOWN_LIMIT = 5000;
  const OVERLAY_STYLE = 'position:absolute;inset:0;width:100%;height:100%;object-fit:cover;border-radius:inherit;'
    + 'pointer-events:none;opacity:0;transition:opacity .2s';

  const known = new Map();
  const attempts = new Map();
  const failed = new Set();
  const waiting = new Set();
  let flushTimer = null;

  const videoOf = (element) => VIDEO_IN_URL.exec(element.style.backgroundImage)?.[1] ?? null;
  const overlayOf = (element) => Array.from(element.children).find((child) => child.classList.contains(OVERLAY)) ?? null;

  /** The overlay is positioned against its thumbnail, so a static thumbnail becomes relative. */
  function keepPositioned(element) {
    if (element.dataset.steamosYtStatic === undefined) {
      element.dataset.steamosYtStatic = getComputedStyle(element).position === 'static' ? '1' : '0';
    }
    if (element.dataset.steamosYtStatic === '1' && !element.style.position) {
      element.style.position = 'relative';
    }
  }

  function lay(element, videoId, url) {
    keepPositioned(element);
    const overlay = document.createElement('img');
    overlay.className = OVERLAY;
    overlay.dataset.video = videoId;
    overlay.alt = '';
    overlay.decoding = 'async';
    overlay.style.cssText = OVERLAY_STYLE;
    overlay.addEventListener('load', () => {
      overlay.style.opacity = '1';
    }, { once: true });
    overlay.addEventListener('error', () => {
      failed.add(url);
      overlay.remove();
    }, { once: true });
    overlay.src = url;
    element.prepend(overlay);
  }

  function update(element) {
    const videoId = videoOf(element);
    const overlay = overlayOf(element);
    if (overlay && overlay.dataset.video === videoId) {
      keepPositioned(element);
      return;
    }
    overlay?.remove();
    if (!videoId) {
      return;
    }
    if (!known.has(videoId)) {
      waiting.add(videoId);
      flushTimer ??= setTimeout(flush, BATCH_MS);
      return;
    }
    const url = known.get(videoId);
    if (url && !failed.has(url)) {
      lay(element, videoId, url);
    }
  }

  function remember(videoId, url) {
    known.set(videoId, url);
    attempts.delete(videoId);
    while (known.size > KNOWN_LIMIT) {
      known.delete(known.keys().next().value);
    }
  }

  async function flush() {
    flushTimer = null;
    const videoIds = [...waiting].filter((id) => !known.has(id));
    waiting.clear();
    if (videoIds.length === 0) {
      return;
    }
    let urls = {};
    try {
      const response = await chrome.runtime.sendMessage({ type: 'api', method: 'thumbnails', params: { videoIds } });
      urls = response?.result ?? {};
    } catch (error) {
      console.debug('steamos-yt: DeArrow thumbnail lookup failed', error);
    }
    const retry = [];
    for (const id of videoIds) {
      if (Object.hasOwn(urls, id)) {
        remember(id, urls[id]);
      } else if ((attempts.get(id) ?? 0) + 1 < ATTEMPTS) {
        attempts.set(id, (attempts.get(id) ?? 0) + 1);
        retry.push(id);
      }
    }
    if (retry.length > 0) {
      setTimeout(() => {
        retry.forEach((id) => waiting.add(id));
        flushTimer ??= setTimeout(flush, BATCH_MS);
      }, RETRY_MS);
    }
    const looked = new Set(videoIds);
    for (const element of document.getElementsByTagName(THUMBNAIL)) {
      if (looked.has(videoOf(element))) {
        update(element);
      }
    }
  }

  function start() {
    const observer = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === 'attributes') {
          if (record.target.localName === THUMBNAIL) {
            update(record.target);
          }
          continue;
        }
        for (const node of record.addedNodes) {
          if (node.nodeType !== Node.ELEMENT_NODE) {
            continue;
          }
          if (node.localName === THUMBNAIL) {
            update(node);
          }
          for (const element of node.getElementsByTagName(THUMBNAIL)) {
            update(element);
          }
        }
      }
    });
    observer.observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ['style'] });
    for (const element of document.getElementsByTagName(THUMBNAIL)) {
      update(element);
    }
  }

  chrome.runtime.sendMessage({ type: 'settings' }).then((settings) => {
    if (settings?.deArrowThumbnails) {
      start();
    }
  }, (error) => console.debug('steamos-yt: no settings for DeArrow thumbnails', error));
})();
