/**
 * SponsorBlock, DeArrow and Return YouTube Dislike for YouTube on TV.
 *
 * The official extensions read the desktop site's page structure, which the TV
 * interface (Leanback) does not use. These integrations work with Leanback
 * directly: DeArrow titles and thumbnails and Return YouTube Dislike counts are
 * written into the innertube responses Leanback renders from, and SponsorBlock
 * follows the <video> element on Leanback's #/watch route. Every network
 * request runs in the extension's service worker (see api.js).
 */
(() => {
  'use strict';

  const core = window.__steamosYt;
  if (!core || window.__steamosYtServices) {
    return;
  }
  Object.defineProperty(window, '__steamosYtServices', { value: true });

  const config = core.config;
  const VIDEO_ID = /^[\w-]{11}$/;
  const RPC_TIMEOUT_MS = 8000;
  const DEARROW_BUDGET_MS = 1500;
  const DISLIKES_TIMEOUT_MS = 2500;
  const SKIP_WINDOW_S = 2;
  const DEARROW_THUMBNAILS = 'https://dearrow-thumb.ajay.app/api/v1/getThumbnail';
  const PROGRESS_BAR = 'ytlr-progress-bar [idomkey="slider"]';
  const CHAPTER_PIECES = 'ytlr-multi-markers-player-bar-renderer [idomkey="progress-bar"] > [idomkey^="chapter-"]';
  const SEGMENTS = {
    sponsor: { colour: '#00d400', name: 'sponsor' },
    selfpromo: { colour: '#ffff00', name: 'self-promotion' },
    interaction: { colour: '#cc00ff', name: 'interaction reminder' },
    intro: { colour: '#00ffff', name: 'intro' },
    outro: { colour: '#0202ed', name: 'outro' },
    preview: { colour: '#008fd6', name: 'preview' },
    hook: { colour: '#395699', name: 'hook' },
    filler: { colour: '#7300ff', name: 'tangent' },
    music_offtopic: { colour: '#ff9900', name: 'non-music section' },
  };

  const pendingCalls = new Map();
  let nextCall = 0;

  window.addEventListener('message', (event) => {
    const data = event.data;
    if (event.source !== window || data?.source !== 'steamos-yt' || data.direction !== 'response') {
      return;
    }
    const call = pendingCalls.get(data.id);
    if (!call) {
      return;
    }
    pendingCalls.delete(data.id);
    clearTimeout(call.timer);
    if (data.error) {
      call.reject(new Error(data.error));
    } else {
      call.resolve(data.result);
    }
  });

  function rpc(method, params, timeoutMs = RPC_TIMEOUT_MS) {
    return new Promise((resolve, reject) => {
      const id = `call-${(nextCall += 1)}`;
      const timer = setTimeout(() => {
        pendingCalls.delete(id);
        reject(new Error(`${method} timed out`));
      }, timeoutMs);
      pendingCalls.set(id, { resolve, reject, timer });
      window.postMessage({ source: 'steamos-yt', direction: 'request', id, method, params }, window.location.origin);
    });
  }

  function walk(root, visit) {
    const stack = [root];
    while (stack.length > 0) {
      const node = stack.pop();
      if (Array.isArray(node)) {
        for (const item of node) {
          if (item && typeof item === 'object') {
            stack.push(item);
          }
        }
      } else if (node && typeof node === 'object') {
        visit(node);
        for (const key in node) {
          const value = node[key];
          if (value && typeof value === 'object') {
            stack.push(value);
          }
        }
      }
    }
  }

  function setText(text, value) {
    if (!text || typeof text !== 'object') {
      return false;
    }
    if (Array.isArray(text.runs) && !('simpleText' in text)) {
      text.runs = [{ text: value }];
    } else {
      text.simpleText = value;
      delete text.runs;
    }
    return true;
  }

  const formatCount = (count) => new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(count);

  const deArrow = {
    name: 'DeArrow',
    paths: ['/youtubei/v1/browse', '/youtubei/v1/search', '/youtubei/v1/next'],
    async rewrite(data) {
      const tiles = [];
      walk(data, (node) => {
        const tile = node.tileRenderer;
        if (tile?.contentType === 'TILE_CONTENT_TYPE_VIDEO' && VIDEO_ID.test(tile.contentId || '')) {
          tiles.push(tile);
        }
      });
      if (tiles.length === 0) {
        return false;
      }
      const videoIds = [...new Set(tiles.map((tile) => tile.contentId))];
      const brandings = await rpc('brandings', { videoIds, budgetMs: DEARROW_BUDGET_MS }).catch(() => ({}));
      let changed = false;
      for (const tile of tiles) {
        const branding = brandings[tile.contentId];
        if (!branding) {
          continue;
        }
        if (branding.title) {
          changed = setText(tile.metadata?.tileMetadataRenderer?.title, branding.title) || changed;
        }
        const thumbnails = tile.header?.tileHeaderRenderer?.thumbnail?.thumbnails;
        if (config.deArrowThumbnails && branding.thumbnailTime !== null && Array.isArray(thumbnails)) {
          const url = `${DEARROW_THUMBNAILS}?videoID=${tile.contentId}&time=${branding.thumbnailTime}`;
          for (const thumbnail of thumbnails) {
            thumbnail.url = url;
          }
          changed = thumbnails.length > 0 || changed;
        }
      }
      return changed;
    },
  };

  const returnDislikes = {
    name: 'Return YouTube Dislike',
    paths: ['/youtubei/v1/next'],
    async rewrite(data) {
      const videoId = data.currentVideoEndpoint?.watchEndpoint?.videoId;
      if (!VIDEO_ID.test(videoId || '')) {
        return false;
      }
      const buttons = [];
      const headers = [];
      walk(data, (node) => {
        if (node.likeButtonRenderer) {
          buttons.push(node.likeButtonRenderer);
        }
        if (Array.isArray(node.videoDescriptionHeaderRenderer?.factoid)) {
          headers.push(node.videoDescriptionHeaderRenderer);
        }
      });
      if (buttons.length === 0 && headers.length === 0) {
        return false;
      }
      const votes = await rpc('votes', { videoId }, DISLIKES_TIMEOUT_MS).catch(() => null);
      if (!votes) {
        return false;
      }
      const count = formatCount(votes.dislikes);
      for (const button of buttons) {
        button.dislikeCountText = { simpleText: count };
        button.dislikeCountWithUndislikeText = { simpleText: count };
        if (button.dislikeCountWithDislikeText) {
          button.dislikeCountWithDislikeText = { simpleText: formatCount(votes.dislikes + 1) };
        }
      }
      for (const header of headers) {
        header.factoid.push({ factoidRenderer: { value: { simpleText: count }, label: { simpleText: 'Dislikes' } } });
      }
      return true;
    },
  };

  /**
   * Leanback loads innertube data with XMLHttpRequest. Requests for the paths a
   * rewriter handles hold back their completion events until the response has
   * been rewritten; every other request behaves exactly as before.
   */
  function installResponseRewriting(rewriters) {
    const NativeXHR = window.XMLHttpRequest;
    const proto = NativeXHR.prototype;
    const nativeText = Object.getOwnPropertyDescriptor(proto, 'responseText').get;
    const nativeResponse = Object.getOwnPropertyDescriptor(proto, 'response').get;
    const nativeOpen = proto.open;
    const nativeAdd = proto.addEventListener;
    const nativeRemove = proto.removeEventListener;
    const COMPLETION_EVENTS = ['readystatechange', 'load', 'loadend'];

    const rewritersFor = (url) => {
      let path;
      try {
        path = new URL(url, window.location.href).pathname;
      } catch {
        return [];
      }
      return rewriters.filter((rewriter) => rewriter.paths.includes(path));
    };

    const invoke = (listener, target, event) => {
      if (typeof listener === 'function') {
        listener.call(target, event);
      } else if (listener && typeof listener.handleEvent === 'function') {
        listener.handleEvent(event);
      }
    };

    function XMLHttpRequest() {
      const xhr = new NativeXHR();
      const wrapped = Object.fromEntries(COMPLETION_EVENTS.map((type) => [type, new WeakMap()]));
      let active = [];
      let generation = 0;
      let rewriting = null;
      let rewritten = null;

      const rewrite = () => {
        if (!rewriting) {
          const current = generation;
          rewriting = (async () => {
            const textual = xhr.responseType === '' || xhr.responseType === 'text';
            if (!textual || xhr.status < 200 || xhr.status >= 300) {
              return;
            }
            let data;
            try {
              data = JSON.parse(nativeText.call(xhr));
            } catch {
              return;
            }
            let changed = false;
            for (const rewriter of active) {
              try {
                changed = (await rewriter.rewrite(data)) || changed;
              } catch (error) {
                console.warn(`steamos-yt: ${rewriter.name} failed`, error);
              }
            }
            if (changed && current === generation) {
              rewritten = JSON.stringify(data);
            }
          })();
        }
        return rewriting;
      };

      const wrap = (listener) => function completionListener(event) {
        if (xhr.readyState !== 4 || active.length === 0) {
          invoke(listener, this, event);
          return;
        }
        const current = generation;
        rewrite().finally(() => {
          if (current === generation) {
            invoke(listener, xhr, event);
          }
        });
      };

      const wrapperFor = (type, listener) => {
        if (!wrapped[type].has(listener)) {
          wrapped[type].set(listener, wrap(listener));
        }
        return wrapped[type].get(listener);
      };

      xhr.addEventListener = function addEventListener(type, listener, options) {
        if (COMPLETION_EVENTS.includes(type) && listener) {
          return nativeAdd.call(xhr, type, wrapperFor(type, listener), options);
        }
        return nativeAdd.call(xhr, type, listener, options);
      };

      xhr.removeEventListener = function removeEventListener(type, listener, options) {
        const replacement = COMPLETION_EVENTS.includes(type) && listener ? wrapped[type].get(listener) : null;
        return nativeRemove.call(xhr, type, replacement || listener, options);
      };

      for (const type of COMPLETION_EVENTS) {
        let handler = null;
        let installed = null;
        Object.defineProperty(xhr, `on${type}`, {
          configurable: true,
          enumerable: true,
          get: () => handler,
          set(value) {
            if (installed) {
              nativeRemove.call(xhr, type, installed);
            }
            handler = typeof value === 'function' ? value : null;
            installed = handler ? wrap(handler) : null;
            if (installed) {
              nativeAdd.call(xhr, type, installed);
            }
          },
        });
      }

      for (const [name, getter] of [['responseText', nativeText], ['response', nativeResponse]]) {
        Object.defineProperty(xhr, name, {
          configurable: true,
          enumerable: true,
          get: () => (rewritten !== null ? rewritten : getter.call(xhr)),
        });
      }

      xhr.open = function open(method, url) {
        generation += 1;
        rewriting = null;
        rewritten = null;
        active = rewritersFor(String(url));
        return nativeOpen.apply(xhr, arguments);
      };

      return xhr;
    }

    XMLHttpRequest.prototype = proto;
    for (const key of ['UNSENT', 'OPENED', 'HEADERS_RECEIVED', 'LOADING', 'DONE']) {
      XMLHttpRequest[key] = NativeXHR[key];
    }
    window.XMLHttpRequest = XMLHttpRequest;
  }

  function watchedVideoId() {
    const [path, query = ''] = window.location.hash.replace(/^#/, '').split('?');
    if (!path.startsWith('/watch')) {
      return null;
    }
    const id = new URLSearchParams(query).get('v');
    return id && VIDEO_ID.test(id) ? id : null;
  }

  function gradient(segments, from, to) {
    const span = to - from;
    const layers = [...segments]
      .sort((a, b) => (a.end - a.start) - (b.end - b.start))
      .filter((segment) => segment.end > from && segment.start < to)
      .map((segment) => {
        const colour = SEGMENTS[segment.category]?.colour || '#ffffff';
        const start = Math.max(0, ((segment.start - from) / span) * 100).toFixed(3);
        const end = Math.min(100, ((segment.end - from) / span) * 100).toFixed(3);
        return `linear-gradient(to right, transparent ${start}%, ${colour} ${start}%, ${colour} ${end}%, transparent ${end}%)`;
      });
    return layers.join(', ') || 'none';
  }

  function chapterRanges(duration) {
    const pieces = [...document.querySelectorAll(CHAPTER_PIECES)];
    const widths = pieces.map((piece) => parseFloat(piece.style.width) || 0);
    const total = widths.reduce((sum, width) => sum + width, 0);
    if (pieces.length === 0 || !(total > 0)) {
      return [];
    }
    let offset = 0;
    return pieces.map((piece, index) => {
      const range = {
        key: piece.getAttribute('idomkey'),
        from: (offset / total) * duration,
        to: ((offset + widths[index]) / total) * duration,
      };
      offset += widths[index];
      return range;
    });
  }

  function installSponsorBlock(categories) {
    const sheet = new CSSStyleSheet();
    document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
    let videoId = null;
    let segments = [];
    let video = null;
    let attachTimer = 0;
    let drawnChapters = '';

    const draw = () => {
      const duration = video?.duration;
      if (segments.length === 0 || !Number.isFinite(duration) || duration <= 0) {
        sheet.replaceSync('');
        drawnChapters = '';
        return;
      }
      const chapters = chapterRanges(duration);
      drawnChapters = JSON.stringify(chapters);
      const overlay = 'content: ""; position: absolute; inset: 0; pointer-events: none; opacity: 0.7;';
      const rules = [`${PROGRESS_BAR}::after { ${overlay} background: ${gradient(segments, 0, duration)}; }`];
      for (const chapter of chapters) {
        const selector = `ytlr-multi-markers-player-bar-renderer [idomkey="${CSS.escape(chapter.key)}"]::after`;
        rules.push(`${selector} { ${overlay} background: ${gradient(segments, chapter.from, chapter.to)}; }`);
      }
      sheet.replaceSync(rules.join('\n'));
    };

    const skip = () => {
      if (!video || segments.length === 0) {
        return;
      }
      const time = video.currentTime;
      const segment = segments.find((item) => time >= item.start && time < item.end && time < item.start + SKIP_WINDOW_S);
      if (!segment) {
        return;
      }
      video.currentTime = segment.end;
      core.toast('SponsorBlock', `Skipped ${SEGMENTS[segment.category]?.name || segment.category}`);
    };

    const attach = () => {
      clearTimeout(attachTimer);
      const element = document.querySelector('video');
      if (!element) {
        attachTimer = setTimeout(attach, 250);
        return;
      }
      if (element !== video) {
        video?.removeEventListener('timeupdate', skip);
        video?.removeEventListener('durationchange', draw);
        video = element;
        video.addEventListener('timeupdate', skip);
        video.addEventListener('durationchange', draw);
      }
      draw();
    };

    const onRoute = () => {
      const id = watchedVideoId();
      if (id === videoId) {
        return;
      }
      videoId = id;
      segments = [];
      draw();
      if (!id) {
        return;
      }
      rpc('segments', { videoId: id, categories }).then((result) => {
        if (videoId === id) {
          segments = Array.isArray(result) ? result.sort((a, b) => a.start - b.start) : [];
          attach();
        }
      }, (error) => console.warn('steamos-yt: SponsorBlock lookup failed', error));
    };

    setInterval(() => {
      if (segments.length > 0 && video && JSON.stringify(chapterRanges(video.duration)) !== drawnChapters) {
        draw();
      }
    }, 1000);
    window.addEventListener('hashchange', onRoute);
    onRoute();
  }

  const rewriters = [config.deArrow && deArrow, config.returnDislikes && returnDislikes].filter(Boolean);
  if (rewriters.length > 0) {
    installResponseRewriting(rewriters);
  }
  if (config.sponsorBlock && config.sponsorBlockCategories?.length > 0) {
    installSponsorBlock(config.sponsorBlockCategories);
  }
})();
