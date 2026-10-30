/**
 * Ad removal for YouTube on TV (Leanback).
 *
 * Leanback reads innertube responses with JSON.parse. Before it sees them,
 * this script drops the home page's masthead ad (a tvMastheadRenderer or
 * adSlotRenderer section), promoted shelves, sponsored tiles in feeds, search
 * results and suggestions, ads among Shorts, and each video's ad schedule
 * (adPlacements, adSlots and playerAds), so no video ads play. These are the
 * structures the webOS, Tizen and VacuumTube clients for YouTube on TV remove;
 * responses are cleaned at any depth, so continuations are covered as well.
 */
(() => {
  'use strict';

  if (globalThis.__STEAMOS_YT_CONFIG__?.blockAds === false || window.__steamosYtAds) {
    return;
  }
  Object.defineProperty(window, '__steamosYtAds', { value: true });

  const AD_RENDERERS = ['adSlotRenderer', 'tvMastheadRenderer', 'promoShelfRenderer'];
  const PLAYER_ADS = ['adPlacements', 'adSlots', 'playerAds'];

  const isObject = (value) => value !== null && typeof value === 'object';
  const isAd = (item) => isObject(item)
    && (AD_RENDERERS.some((key) => key in item) || item.command?.reelWatchEndpoint?.adClientParams?.isAd === true);
  const isInnertube = (value) => isObject(value) && !Array.isArray(value)
    && ('responseContext' in value || PLAYER_ADS.some((key) => key in value));

  function strip(node) {
    if (Array.isArray(node)) {
      for (let index = node.length - 1; index >= 0; index -= 1) {
        if (isAd(node[index])) {
          node.splice(index, 1);
        } else {
          strip(node[index]);
        }
      }
      return;
    }
    if (!isObject(node)) {
      return;
    }
    for (const key of PLAYER_ADS) {
      if (key in node) {
        delete node[key];
      }
    }
    for (const value of Object.values(node)) {
      strip(value);
    }
  }

  function clean(value) {
    if (isInnertube(value)) {
      try {
        strip(value);
      } catch (error) {
        console.warn('steamos-yt: could not remove ads', error);
      }
    }
    return value;
  }

  const nativeParse = JSON.parse;
  JSON.parse = function parse(text, reviver) {
    return clean(nativeParse.call(this, text, reviver));
  };

  const nativeJson = Response.prototype.json;
  Response.prototype.json = function json() {
    return nativeJson.call(this).then(clean);
  };
})();
