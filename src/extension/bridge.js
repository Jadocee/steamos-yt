'use strict';

(() => {
  const SOURCE = 'steamos-yt';

  const reply = (id, response) => {
    window.postMessage({ source: SOURCE, direction: 'response', id, ...response }, window.location.origin);
  };

  window.addEventListener('message', (event) => {
    const data = event.data;
    if (event.source !== window || data?.source !== SOURCE) {
      return;
    }
    if (data.type === 'exit') {
      chrome.runtime.sendMessage({ type: 'exit', reason: String(data.reason || '') }).catch(() => {});
    } else if (data.direction === 'request' && typeof data.method === 'string') {
      chrome.runtime.sendMessage({ type: 'api', method: data.method, params: data.params })
        .then(
          (response) => reply(data.id, response || { error: 'no response' }),
          (error) => reply(data.id, { error: String(error?.message || error) }),
        );
    }
  });
})();
