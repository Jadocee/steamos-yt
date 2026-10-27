'use strict';

importScripts('api.js');

const TV_URL = /^https:\/\/www\.youtube\.com\/tv(?:[/?#]|$)/;
const SPLASH_MARKER = 'steamos-yt-splash';
const RULES_TIMEOUT_MS = 4000;

const urlOf = (tab) => (tab && (tab.url || tab.pendingUrl)) || '';
const isTv = (tab) => TV_URL.test(urlOf(tab));
const isSplash = (tab) => urlOf(tab).startsWith('data:text/html') && urlOf(tab).includes(SPLASH_MARKER);

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
    const splashTabs = (await chrome.tabs.query({})).filter(isSplash);
    if (splashTabs.length === 0) {
      return;
    }
    await rulesReady(config.targetUrl, config);
    await Promise.all(splashTabs.map((tab) => chrome.tabs.update(tab.id, { url: config.targetUrl })));
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
  if (message?.type === 'api') {
    return answerApi(message, sendResponse);
  }
  return false;
});

chrome.tabs.onCreated.addListener((tab) => {
  if (isSplash(tab)) {
    leaveSplash();
  } else {
    guardPopup(tab);
  }
});

chrome.tabs.onUpdated.addListener((tabId, change, tab) => {
  if (change.url && isSplash(tab)) {
    leaveSplash();
  }
});

chrome.runtime.onStartup.addListener(leaveSplash);
chrome.runtime.onInstalled.addListener(leaveSplash);
leaveSplash();
