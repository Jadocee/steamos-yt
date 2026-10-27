/**
 * Main-world companion for YouTube on TV (Leanback) inside the SteamOS kiosk.
 *
 * Leanback expects to run on Cobalt, which turns controller input into
 * Starboard key codes (0x8000 + standard gamepad button index) and answers
 * media capability probes with real device limits. This script recreates both
 * inside Helium, adds pointer conveniences, and routes Leanback's exit request
 * to the extension so the kiosk closes and Steam takes focus again.
 */
(() => {
  'use strict';

  if (window.__steamosYt) {
    return;
  }

  const config = {
    controller: true,
    cursorHideMs: 3000,
    maxResolution: 'auto',
    blockCodecs: [],
    exitCombo: true,
    identity: null,
    ...globalThis.__STEAMOS_YT_CONFIG__,
  };

  const STARBOARD_GAMEPAD = 0x8000;
  const BUTTON = Object.freeze({
    A: 0, B: 1, X: 2, Y: 3, LB: 4, RB: 5, LT: 6, RT: 7, VIEW: 8, MENU: 9,
    L3: 10, R3: 11, UP: 12, DOWN: 13, LEFT: 14, RIGHT: 15, GUIDE: 16,
  });
  const STICKS = [[19, 20], [17, 18], [23, 24], [21, 22]];
  const REPEATABLE = new Set([12, 13, 14, 15, 17, 18, 19, 20, 21, 22, 23, 24]);
  const STEAM_VIRTUAL_PAD = /Vendor: 28de Product: 11ff/i;
  const AXIS_THRESHOLD = 0.5;
  const REPEAT_DELAY_MS = 450;
  const REPEAT_INTERVAL_MS = 110;
  const EXIT_HOLD_MS = 1500;
  const TAP_MS = 60;
  const CODEC_PATTERNS = { av1: /av01/i, vp9: /vp0?9/i, vp8: /vp0?8/i, h264: /avc[13]/i };
  const CONTAINER_SIZES = ['1280x720', '1920x1080', '2560x1440', '3840x2160', '7680x4320'];

  const api = {
    version: config.version || 'dev',
    config: Object.freeze({ ...config }),
    requestExit,
  };
  Object.defineProperty(window, '__steamosYt', { value: Object.freeze(api) });

  function emitKey(type, code) {
    const event = new Event(type, { cancelable: true });
    Object.defineProperties(event, {
      keyCode: { value: code },
      which: { value: code },
    });
    document.dispatchEvent(event);
  }

  function tap(button) {
    emitKey('keydown', STARBOARD_GAMEPAD + button);
    setTimeout(() => emitKey('keyup', STARBOARD_GAMEPAD + button), TAP_MS);
  }

  function requestExit(reason = 'request') {
    window.postMessage({ source: 'steamos-yt', type: 'exit', reason }, window.location.origin);
  }

  function installExitHandling() {
    const nativeClose = window.close;
    window.close = function close() {
      requestExit('window.close');
      setTimeout(() => nativeClose.call(window), 1500);
    };

    const isExitCommand = (command) => {
      if (!command || typeof command !== 'object') {
        return false;
      }
      if (command.signalAction?.signal === 'EXIT_APP') {
        return true;
      }
      const nested = command.commandExecutorCommand?.commands;
      return Array.isArray(nested) && nested.some(isExitCommand);
    };

    const wrap = (instance) => {
      const original = instance.resolveCommand;
      if (original.__steamosYt) {
        return;
      }
      const resolveCommand = function resolveCommand(command, ...rest) {
        if (isExitCommand(command)) {
          requestExit('leanback');
          return true;
        }
        return original.apply(this, [command, ...rest]);
      };
      Object.defineProperty(resolveCommand, '__steamosYt', { value: true });
      instance.resolveCommand = resolveCommand;
    };

    const started = Date.now();
    const timer = setInterval(() => {
      const registry = window._yttv;
      const instance = registry && typeof registry === 'object'
        ? Object.values(registry).map((entry) => entry?.instance).find((item) => typeof item?.resolveCommand === 'function')
        : undefined;
      if (instance) {
        wrap(instance);
        clearInterval(timer);
      } else if (Date.now() - started > 120000) {
        clearInterval(timer);
      }
    }, 250);
  }

  function installIdentity(identity) {
    if (!identity || !('userAgentData' in Navigator.prototype)) {
      return;
    }
    const brands = Object.freeze([Object.freeze({ brand: identity.brand, version: identity.majorVersion })]);
    const fullVersionList = Object.freeze([Object.freeze({ brand: identity.brand, version: identity.fullVersion })]);
    const lowEntropy = () => ({ brands, mobile: false, platform: identity.platform });
    const highEntropy = {
      architecture: identity.architecture,
      bitness: identity.bitness,
      formFactors: Object.freeze([]),
      fullVersionList,
      model: '',
      platformVersion: '',
      uaFullVersion: identity.fullVersion,
      wow64: false,
    };
    const prototype = typeof NavigatorUAData === 'function' ? NavigatorUAData.prototype : Object.prototype;
    const userAgentData = Object.create(prototype, {
      brands: { value: brands, enumerable: true },
      mobile: { value: false, enumerable: true },
      platform: { value: identity.platform, enumerable: true },
      getHighEntropyValues: {
        value: function getHighEntropyValues(hints) {
          const values = lowEntropy();
          for (const hint of Array.isArray(hints) ? hints : []) {
            if (Object.hasOwn(highEntropy, hint)) {
              values[hint] = highEntropy[hint];
            }
          }
          return Promise.resolve(values);
        },
      },
      toJSON: { value: lowEntropy },
    });
    Object.defineProperty(Navigator.prototype, 'userAgentData', {
      configurable: true,
      enumerable: true,
      get: () => userAgentData,
    });
  }

  function installMediaCapabilities() {
    const blocked = (config.blockCodecs || []).filter((codec) => CODEC_PATTERNS[codec]);
    const isBlocked = (type) => blocked.some((codec) => CODEC_PATTERNS[codec].test(type));
    const isHdrDisplay = () => window.matchMedia('(dynamic-range: high)').matches;
    const isHdrCodec = (codec) => {
      const parts = codec.trim().split('.');
      const transfer = parts[0] === 'vp09' ? parts[6] : parts[0] === 'av01' ? parts[7] : undefined;
      return transfer === '16' || transfer === '18';
    };
    const numericLimits = {
      width: 7680,
      height: 4320,
      framerate: 60,
      bitrate: 200000000,
      channels: 8,
    };
    const textChecks = {
      eotf: (value) => value === 'bt709' || ((value === 'smpte2084' || value === 'arib-std-b67') && isHdrDisplay()),
      cryptoblockformat: (value) => value === 'subsample',
      'decode-to-texture': (value) => value === 'true' || value === 'false',
    };

    const mediaSource = window.MediaSource;
    if (mediaSource && typeof mediaSource.isTypeSupported === 'function') {
      const nativeIsTypeSupported = mediaSource.isTypeSupported.bind(mediaSource);
      mediaSource.isTypeSupported = function isTypeSupported(type) {
        const text = String(type);
        if (isBlocked(text)) {
          return false;
        }
        const [mime, ...params] = text.split(';').map((part) => part.trim());
        const kept = [mime];
        for (const param of params) {
          if (!param) {
            continue;
          }
          const separator = param.indexOf('=');
          const key = (separator < 0 ? param : param.slice(0, separator)).trim().toLowerCase();
          const value = separator < 0 ? '' : param.slice(separator + 1).trim().replace(/^"|"$/g, '');
          if (key === 'codecs') {
            if (!isHdrDisplay() && value.split(',').some(isHdrCodec)) {
              return false;
            }
            kept.push(param);
          } else if (Object.hasOwn(numericLimits, key)) {
            const number = Number(value);
            if (!Number.isFinite(number) || number <= 0 || number > numericLimits[key]) {
              return false;
            }
          } else if (Object.hasOwn(textChecks, key)) {
            if (!textChecks[key](value.toLowerCase())) {
              return false;
            }
          } else {
            kept.push(param);
          }
        }
        return nativeIsTypeSupported(kept.join('; '));
      };
    }

    if (!blocked.length) {
      return;
    }
    const nativeCanPlayType = HTMLMediaElement.prototype.canPlayType;
    HTMLMediaElement.prototype.canPlayType = function canPlayType(type) {
      return isBlocked(String(type)) ? '' : nativeCanPlayType.call(this, type);
    };
    const capabilities = navigator.mediaCapabilities;
    if (capabilities && typeof capabilities.decodingInfo === 'function') {
      const nativeDecodingInfo = capabilities.decodingInfo.bind(capabilities);
      capabilities.decodingInfo = function decodingInfo(configuration) {
        const types = [configuration?.video?.contentType, configuration?.audio?.contentType].filter(Boolean);
        if (types.some((type) => isBlocked(String(type)))) {
          return Promise.resolve({ supported: false, smooth: false, powerEfficient: false });
        }
        return nativeDecodingInfo(configuration);
      };
    }
  }

  function installContainerSizeOverride() {
    const setting = config.maxResolution;
    if (!setting || setting === 'auto' || window.h5vcc) {
      return;
    }
    let size = setting;
    if (setting === 'screen') {
      const ratio = window.devicePixelRatio || 1;
      const long = Math.max(screen.width, screen.height) * ratio;
      const short = Math.min(screen.width, screen.height) * ratio;
      size = CONTAINER_SIZES.find((candidate) => {
        const [width, height] = candidate.split('x').map(Number);
        return long <= width && short <= height;
      }) || CONTAINER_SIZES[CONTAINER_SIZES.length - 1];
    }
    window.h5vcc = {
      runtime: { initialDeepLink: null, onDeepLink: { addListener() {} } },
      system: { getVideoContainerSizeOverride: () => size },
    };
  }

  function installPointerSupport(hooks) {
    const sheet = new CSSStyleSheet();
    sheet.replaceSync('[data-steamos-yt-cursor-hidden], [data-steamos-yt-cursor-hidden] * { cursor: none !important; }');
    document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];

    const root = document.documentElement;
    let hideTimer = 0;
    const hideCursor = () => root.toggleAttribute('data-steamos-yt-cursor-hidden', true);
    const showCursor = () => {
      root.removeAttribute('data-steamos-yt-cursor-hidden');
      clearTimeout(hideTimer);
      if (config.cursorHideMs > 0) {
        hideTimer = setTimeout(hideCursor, config.cursorHideMs);
      }
    };
    if (config.cursorHideMs > 0) {
      hideCursor();
      hooks.onControllerInput = hideCursor;
    }
    const onPointer = (event) => {
      if (event.type === 'pointermove' && event.movementX === 0 && event.movementY === 0) {
        return;
      }
      showCursor();
    };
    for (const type of ['pointermove', 'pointerdown']) {
      window.addEventListener(type, onPointer, { capture: true, passive: true });
    }

    let wheelLocked = false;
    window.addEventListener('wheel', (event) => {
      if (event.ctrlKey) {
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();
      const horizontal = Math.abs(event.deltaX) > Math.abs(event.deltaY);
      const delta = horizontal ? event.deltaX : event.deltaY;
      if (wheelLocked || !delta) {
        return;
      }
      if (horizontal) {
        tap(delta < 0 ? BUTTON.LEFT : BUTTON.RIGHT);
      } else {
        tap(delta < 0 ? BUTTON.UP : BUTTON.DOWN);
      }
      wheelLocked = true;
      setTimeout(() => {
        wheelLocked = false;
      }, 120);
    }, { capture: true, passive: false });

    window.addEventListener('contextmenu', (event) => event.preventDefault(), true);
    window.addEventListener('mousedown', (event) => {
      if (event.button === 2 || event.button === 3) {
        event.preventDefault();
        tap(BUTTON.B);
      }
    }, true);
  }

  function installControllerBridge(hooks) {
    const pads = new Map();
    let repeating = null;
    let exitTimer = 0;

    const stopRepeat = () => {
      if (repeating) {
        clearTimeout(repeating.timer);
        repeating = null;
      }
    };

    const startRepeat = (button) => {
      stopRepeat();
      const state = { button, timer: 0 };
      const tick = () => {
        emitKey('keydown', STARBOARD_GAMEPAD + button);
        state.timer = setTimeout(tick, REPEAT_INTERVAL_MS);
      };
      state.timer = setTimeout(tick, REPEAT_DELAY_MS);
      repeating = state;
    };

    const press = (button) => {
      hooks.onControllerInput?.();
      emitKey('keydown', STARBOARD_GAMEPAD + button);
      if (REPEATABLE.has(button)) {
        startRepeat(button);
      }
    };

    const release = (button) => {
      emitKey('keyup', STARBOARD_GAMEPAD + button);
      if (repeating?.button === button) {
        stopRepeat();
      }
    };

    const releaseAll = (state) => {
      state.buttons.forEach(release);
      state.buttons.clear();
      state.axes.forEach((button) => button !== null && release(button));
      state.axes.clear();
    };

    const read = (pad) => {
      let state = pads.get(pad.index);
      if (!state) {
        state = { buttons: new Set(), axes: new Map() };
        pads.set(pad.index, state);
      }
      pad.buttons.forEach((control, button) => {
        if (button > BUTTON.GUIDE) {
          return;
        }
        if (control.pressed && !state.buttons.has(button)) {
          state.buttons.add(button);
          press(button);
        } else if (!control.pressed && state.buttons.has(button)) {
          state.buttons.delete(button);
          release(button);
        }
      });
      STICKS.forEach(([negative, positive], axis) => {
        const value = pad.axes[axis] || 0;
        const button = value <= -AXIS_THRESHOLD ? negative : value >= AXIS_THRESHOLD ? positive : null;
        const held = state.axes.has(axis) ? state.axes.get(axis) : null;
        if (button === held) {
          return;
        }
        state.axes.set(axis, button);
        if (held !== null) {
          release(held);
        }
        if (button !== null) {
          press(button);
        }
      });
    };

    const updateExitCombo = () => {
      const held = config.exitCombo && [...pads.values()].some(
        (state) => state.buttons.has(BUTTON.VIEW) && state.buttons.has(BUTTON.MENU),
      );
      if (held && !exitTimer) {
        exitTimer = setTimeout(() => requestExit('controller'), EXIT_HOLD_MS);
      } else if (!held && exitTimer) {
        clearTimeout(exitTimer);
        exitTimer = 0;
      }
    };

    const poll = () => {
      const connected = Array.from(navigator.getGamepads?.() || []).filter((pad) => pad?.connected);
      const virtual = connected.filter((pad) => STEAM_VIRTUAL_PAD.test(pad.id));
      const active = document.visibilityState === 'visible' && document.hasFocus();
      const seen = new Set();
      if (active) {
        for (const pad of virtual.length ? virtual : connected) {
          seen.add(pad.index);
          read(pad);
        }
      }
      for (const [index, state] of pads) {
        if (!seen.has(index)) {
          releaseAll(state);
          pads.delete(index);
        }
      }
      updateExitCombo();
      requestAnimationFrame(poll);
    };
    requestAnimationFrame(poll);
  }

  const hooks = {};
  installIdentity(config.identity);
  installMediaCapabilities();
  installContainerSizeOverride();
  installExitHandling();
  installPointerSupport(hooks);
  if (config.controller) {
    installControllerBridge(hooks);
  }
})();
