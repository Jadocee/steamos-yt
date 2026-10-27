'use strict';

window.addEventListener('message', (event) => {
  const data = event.data;
  if (event.source !== window || data?.source !== 'steamos-yt' || data.type !== 'exit') {
    return;
  }
  chrome.runtime.sendMessage({ type: 'exit', reason: String(data.reason || '') }).catch(() => {});
});
