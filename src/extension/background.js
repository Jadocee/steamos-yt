'use strict';

importScripts('api.js');

const TV_URL = /^https:\/\/www\.youtube\.com\/tv(?:[/?#]|$)/;
const SPLASH_MARKER = 'steamos-yt-splash';
const RULES_TIMEOUT_MS = 4000;
const SPLASH_RESEND_MS = 10000;
const SEND_BACK_REPEAT_MS = 3000;

const urlOf = (tab) => (tab && (tab.url || tab.pendingUrl)) || '';
const isTv = (tab) => TV_URL.test(urlOf(tab));
const isSplashUrl = (url) => url.startsWith('data:text/html') && url.includes(SPLASH_MARKER);
const isSplash = (tab) => isSplashUrl(urlOf(tab));
const sentFromSplash = new Map();

/**
 * The tab shows the boot screen and nothing has sent it on yet. Several events
 * can ask to leave the boot screen at start-up, and a tab keeps reporting the
 * boot screen until the next page commits, so a tab is sent on only once.
 */
function waitingOnSplash(tab) {
  if (!isSplash(tab) || (tab.pendingUrl && !isSplashUrl(tab.pendingUrl))) {
    return false;
  }
  return Date.now() - (sentFromSplash.get(tab.id) ?? 0) > SPLASH_RESEND_MS;
}

let configLoad = null;

/**
 * Settings written at launch. Fetched rather than imported: Chromium serves a
 * service worker's imported scripts from its cache until the extension version
 * changes, which would keep the first launch's settings.
 */
function loadConfig() {
  configLoad ??= fetch(chrome.runtime.getURL('config.json'), { cache: 'no-store' })
    .then((response) => response.json())
    .catch((error) => {
      console.warn('steamos-yt: could not read config.json', error);
      return {};
    });
  return configLoad;
}

async function rulesReady(url, config) {
  if (!config.headerRules) {
    return;
  }
  const deadline = Date.now() + RULES_TIMEOUT_MS;
  while (Date.now() < deadline) {
    try {
      const outcome = await chrome.declarativeNetRequest.testMatchOutcome({ url, type: 'main_frame' });
      if (outcome.matchedRules.length > 0) {
        return;
      }
    } catch (error) {
      console.warn('steamos-yt: cannot confirm the header rules', error);
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  console.warn('steamos-yt: header rules did not become active in time');
}

let leaving = null;

function leaveSplash() {
  leaving ??= (async () => {
    const config = await loadConfig();
    if (!config.targetUrl) {
      return;
    }
    const splashTabs = (await chrome.tabs.query({})).filter(waitingOnSplash);
    if (splashTabs.length === 0) {
      return;
    }
    await rulesReady(config.targetUrl, config);
    await Promise.all(
      splashTabs.map(async (tab) => {
        const current = await chrome.tabs.get(tab.id).catch(() => null);
        if (current && waitingOnSplash(current)) {
          sentFromSplash.set(tab.id, Date.now());
          await chrome.tabs.update(tab.id, { url: config.targetUrl });
        }
      }),
    );
  })()
    .catch((error) => console.warn('steamos-yt: could not leave the boot screen', error))
    .finally(() => {
      leaving = null;
    });
  return leaving;
}

async function closeKiosk() {
  const windows = await chrome.windows.getAll();
  await Promise.allSettled(windows.map((window) => chrome.windows.remove(window.id)));
}

async function guardPopup(tab) {
  if (tab.openerTabId === undefined) {
    return;
  }
  try {
    const opener = await chrome.tabs.get(tab.openerTabId);
    if (!isTv(opener)) {
      return;
    }
    await chrome.tabs.remove(tab.id);
    await chrome.tabs.update(opener.id, { active: true });
    await chrome.windows.update(opener.windowId, { focused: true });
  } catch (error) {
    console.debug('steamos-yt: popup guard skipped', error);
  }
}

const sentBack = new Map();
const onSite = (host, site) => host === site || host.endsWith(`.${site}`);
const kioskTab = (tab) => isTv(tab) || isSplash(tab);

/** Pages the kiosk may show: the boot screen, the allowed sites and Google's "unusual traffic" check. */
function allowedPage(url, config) {
  if (isSplashUrl(url)) {
    return true;
  }
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return false;
  }
  if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
    return false;
  }
  return (config.allowedSites || []).some((site) => onSite(parsed.hostname, site))
    || (onSite(parsed.hostname, 'google.com') && parsed.pathname.startsWith('/sorry/'));
}

/**
 * Closes every tab but the kiosk's: pop-ups, new tabs and new windows from
 * keyboard shortcuts. The kiosk tab is the oldest one showing the boot screen
 * or YouTube on TV; tab IDs only grow during a session.
 */
async function keepOneTab(tabs) {
  const byAge = [...tabs].sort((left, right) => left.id - right.id);
  const keep = byAge.find(kioskTab) ?? byAge[0];
  await Promise.allSettled(tabs.filter((tab) => tab.id !== keep.id).map((tab) => chrome.tabs.remove(tab.id)));
  await chrome.tabs.update(keep.id, { active: true }).catch(() => {});
  await chrome.windows.update(keep.windowId, { focused: true }).catch(() => {});
}

/**
 * Returns the kiosk tab from another site or a browser page (such as the new
 * tab page) to where it was, or to the start page when going back would land
 * somewhere disallowed again.
 */
async function sendBack(tabId, config) {
  const last = sentBack.get(tabId) ?? 0;
  sentBack.set(tabId, Date.now());
  const wentBack = Date.now() - last > SEND_BACK_REPEAT_MS
    && await chrome.tabs.goBack(tabId).then(() => true, () => false);
  if (!wentBack) {
    await chrome.tabs.update(tabId, { url: config.targetUrl || 'https://www.youtube.com/tv' });
  }
}

/**
 * Keeps the kiosk on YouTube when other sites are blocked. Their pages never
 * load (a declarativeNetRequest rule blocks them); this handles what the rule
 * cannot see: extra tabs and windows, and browser pages in the kiosk tab.
 */
async function enforceSiteLock(tab, changedUrl) {
  const config = await loadConfig();
  if (!config.blockOtherSites) {
    return changedUrl ? undefined : guardPopup(tab);
  }
  const tabs = await chrome.tabs.query({});
  if (tabs.length > 1) {
    return keepOneTab(tabs);
  }
  if (changedUrl && !allowedPage(changedUrl, config)) {
    return sendBack(tab.id, config);
  }
  return undefined;
}

function answerApi(message, sendResponse) {
  const api = globalThis.steamosYtApi;
  if (!Object.hasOwn(api, message.method)) {
    sendResponse({ error: `unknown method ${message.method}` });
    return false;
  }
  Promise.resolve()
    .then(() => api[message.method](message.params || {}))
    .then(
      (result) => sendResponse({ result }),
      (error) => sendResponse({ error: String(error?.message || error) }),
    );
  return true;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!isTv(sender.tab)) {
    return false;
  }
  if (message?.type === 'exit') {
    closeKiosk().catch((error) => console.warn('steamos-yt: could not close the kiosk', error));
    return false;
  }
  if (message?.type === 'settings') {
    loadConfig().then((config) => sendResponse({ deArrowThumbnails: Boolean(config.deArrowThumbnails) }));
    return true;
  }
  if (message?.type === 'api') {
    return answerApi(message, sendResponse);
  }
  return false;
});

chrome.tabs.onCreated.addListener((tab) => {
  if (isSplash(tab)) {
    leaveSplash();
  }
  enforceSiteLock(tab).catch((error) => console.debug('steamos-yt: new tab check skipped', error));
});

chrome.tabs.onUpdated.addListener((tabId, change, tab) => {
  if (!change.url) {
    return;
  }
  if (isSplash(tab)) {
    leaveSplash();
  }
  enforceSiteLock(tab, change.url).catch((error) => console.debug('steamos-yt: page check skipped', error));
});

chrome.runtime.onStartup.addListener(leaveSplash);
chrome.runtime.onInstalled.addListener(leaveSplash);
leaveSplash();
