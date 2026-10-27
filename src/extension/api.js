'use strict';

/**
 * Clients for the community services used on YouTube on TV. They run in the
 * service worker, outside the TV page's Content Security Policy, and look
 * videos up by SHA-256 hash prefix where the service supports it.
 *
 * SponsorBlock and DeArrow data: https://sponsor.ajay.app (CC BY-NC-SA 4.0).
 * Dislike counts: https://returnyoutubedislike.com.
 */
const SPONSORBLOCK_SERVER = 'https://sponsor.ajay.app';
const DEARROW_THUMBNAIL_SERVER = 'https://dearrow-thumb.ajay.app';
const RETURN_DISLIKE_SERVER = 'https://returnyoutubedislikeapi.com';
const VIDEO_ID = /^[\w-]{11}$/;
const SEGMENT_CATEGORIES = new Set([
  'sponsor', 'selfpromo', 'interaction', 'intro', 'outro', 'preview', 'hook', 'filler', 'music_offtopic',
]);
const CACHE_TTL_MS = 30 * 60 * 1000;
const FAILURE_TTL_MS = 2 * 60 * 1000;
const CACHE_LIMIT = 3000;
const REQUEST_TIMEOUT_MS = 5000;

const cache = new Map();

function remember(key, load) {
  const hit = cache.get(key);
  if (hit && hit.expires > Date.now()) {
    return hit.value;
  }
  const value = load();
  cache.set(key, { expires: Date.now() + CACHE_TTL_MS, value });
  value.catch(() => cache.set(key, { expires: Date.now() + FAILURE_TTL_MS, value }));
  while (cache.size > CACHE_LIMIT) {
    cache.delete(cache.keys().next().value);
  }
  return value;
}

async function getJson(url) {
  const response = await fetch(url, { credentials: 'omit', signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`${new URL(url).host} answered HTTP ${response.status}`);
  }
  return response.json();
}

async function hashPrefix(videoId) {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(videoId)));
  return Array.from(digest.subarray(0, 2), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

function segments(videoId, categories) {
  const wanted = [...new Set(categories)].filter((category) => SEGMENT_CATEGORIES.has(category)).sort();
  if (!VIDEO_ID.test(videoId) || wanted.length === 0) {
    return Promise.resolve([]);
  }
  return remember(`segments:${videoId}:${wanted}`, async () => {
    const query = new URLSearchParams({ categories: JSON.stringify(wanted), actionTypes: JSON.stringify(['skip']) });
    const matches = (await getJson(`${SPONSORBLOCK_SERVER}/api/skipSegments/${await hashPrefix(videoId)}?${query}`)) || [];
    const entry = matches.find((item) => item.videoID === videoId);
    return (entry?.segments || [])
      .filter((item) => Array.isArray(item.segment) && item.segment[1] > item.segment[0])
      .map((item) => ({ start: item.segment[0], end: item.segment[1], category: item.category }));
  });
}

const usable = (submission) => Boolean(submission) && (submission.locked || submission.votes >= 0);
const cleanTitle = (title) => title.replace(/(^|\s)>(?=\S)/g, '$1').trim();

function branding(videoId) {
  return remember(`branding:${videoId}`, async () => {
    const all = await getJson(`${SPONSORBLOCK_SERVER}/api/branding/${await hashPrefix(videoId)}`);
    const data = all?.[videoId];
    if (!data) {
      return null;
    }
    const [title] = data.titles || [];
    const [thumbnail] = data.thumbnails || [];
    const result = {
      title: usable(title) && !title.original && typeof title.title === 'string' ? cleanTitle(title.title) : null,
      thumbnailTime: usable(thumbnail) && !thumbnail.original && Number.isFinite(thumbnail.timestamp)
        ? thumbnail.timestamp
        : null,
    };
    return result.title || result.thumbnailTime !== null ? result : null;
  });
}

async function brandings(videoIds, budgetMs) {
  const ids = [...new Set(videoIds)].filter((id) => VIDEO_ID.test(id)).slice(0, 300);
  const found = {};
  const lookups = ids.map((id) => branding(id).then((value) => {
    if (value) {
      found[id] = value;
    }
  }, () => {}));
  const budget = Math.min(Math.max(budgetMs, 100), 5000);
  await Promise.race([Promise.all(lookups), new Promise((resolve) => setTimeout(resolve, budget))]);
  return { ...found };
}

/**
 * DeArrow thumbnail URLs for the videos whose lookups finish within the budget:
 * a URL, or null when DeArrow keeps YouTube's thumbnail. Videos still being
 * looked up, or whose lookup failed, are left out so the caller can ask again.
 */
async function thumbnails(videoIds, budgetMs) {
  const ids = [...new Set(videoIds)].filter((id) => VIDEO_ID.test(id)).slice(0, 300);
  const urls = {};
  const lookups = ids.map((id) => branding(id).then((value) => {
    urls[id] = value && value.thumbnailTime !== null
      ? `${DEARROW_THUMBNAIL_SERVER}/api/v1/getThumbnail?videoID=${id}&time=${value.thumbnailTime}`
      : null;
  }, () => {}));
  const budget = Math.min(Math.max(budgetMs, 100), 5000);
  await Promise.race([Promise.all(lookups), new Promise((resolve) => setTimeout(resolve, budget))]);
  return { ...urls };
}

function votes(videoId) {
  if (!VIDEO_ID.test(videoId)) {
    return Promise.resolve(null);
  }
  return remember(`votes:${videoId}`, async () => {
    const data = await getJson(`${RETURN_DISLIKE_SERVER}/votes?videoId=${videoId}`);
    return data && Number.isFinite(data.dislikes) ? { likes: data.likes, dislikes: data.dislikes } : null;
  });
}

globalThis.steamosYtApi = Object.freeze({
  segments: ({ videoId, categories }) => segments(String(videoId), Array.isArray(categories) ? categories.map(String) : []),
  brandings: ({ videoIds, budgetMs }) => brandings(Array.isArray(videoIds) ? videoIds.map(String) : [], Number(budgetMs) || 1500),
  thumbnails: ({ videoIds, budgetMs }) => thumbnails(Array.isArray(videoIds) ? videoIds.map(String) : [], Number(budgetMs) || 5000),
  votes: ({ videoId }) => votes(String(videoId)),
});
