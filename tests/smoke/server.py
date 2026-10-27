#!/usr/bin/env python3
"""HTTPS stand-in for YouTube on TV and its community services, used by the smoke test.

It serves a page at www.youtube.com/tv that inspects what the companion
extension changed, posts the findings back, and then asks the kiosk to exit
through one of the supported paths (Leanback's EXIT_APP command, the controller
combo or window.close). The same server answers for sponsor.ajay.app,
dearrow-thumb.ajay.app and returnyoutubedislikeapi.com.
"""

import argparse
import json
import ssl
import struct
import threading
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

SKIPPED = "dQw4w9WgXcQ"
ORIGINAL = "jNQXAC9IVRw"
DOWNVOTED = "9bZkp7q19f0"
RUNS = "kJQP7kiw5Fk"


def png_pixel():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x33")) + chunk(b"IEND", b"")


PIXEL = png_pixel()


def tile(video_id, title, runs=False):
    text = {"runs": [{"text": title}]} if runs else {"simpleText": title}
    return {
        "tileRenderer": {
            "contentType": "TILE_CONTENT_TYPE_VIDEO",
            "contentId": video_id,
            "metadata": {"tileMetadataRenderer": {"title": text}},
            "header": {
                "tileHeaderRenderer": {
                    "thumbnail": {
                        "thumbnails": [
                            {"url": f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg", "width": 320},
                            {"url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg", "width": 480},
                        ]
                    }
                }
            },
        }
    }


BROWSE = {
    "contents": {
        "tvBrowseRenderer": {
            "content": {
                "tvSurfaceContentRenderer": {
                    "content": {
                        "sectionListRenderer": {
                            "contents": [
                                {
                                    "shelfRenderer": {
                                        "content": {
                                            "horizontalListRenderer": {
                                                "items": [
                                                    tile(SKIPPED, "YOU WON'T BELIEVE THIS"),
                                                    tile(ORIGINAL, "Original title stays"),
                                                    tile(DOWNVOTED, "Downvoted stays"),
                                                    tile(RUNS, "RUNS TITLE", runs=True),
                                                ]
                                            }
                                        }
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        }
    }
}

NEXT = {
    "currentVideoEndpoint": {"watchEndpoint": {"videoId": SKIPPED}},
    "transportControls": {
        "transportControlsRenderer": {
            "engagementActions": [
                {
                    "type": "TRANSPORT_CONTROLS_BUTTON_TYPE_LIKE_BUTTON",
                    "button": {"likeButtonRenderer": {"likeCountText": {"simpleText": "10K"}}},
                }
            ]
        }
    },
    "engagementPanels": [
        {
            "engagementPanelSectionListRenderer": {
                "panelIdentifier": "video-description-ep-identifier",
                "content": {
                    "structuredDescriptionContentRenderer": {
                        "items": [
                            {
                                "videoDescriptionHeaderRenderer": {
                                    "factoid": [
                                        {"factoidRenderer": {"value": {"simpleText": "10K"}, "label": {"simpleText": "Likes"}}}
                                    ]
                                }
                            }
                        ]
                    }
                },
            }
        }
    ],
}

BRANDING = {
    SKIPPED: {
        "titles": [{"title": "An >Honest Title", "original": False, "votes": 3, "locked": False}],
        "thumbnails": [{"timestamp": 42.5, "original": False, "votes": 1, "locked": False}],
        "randomTime": 0.3,
        "videoDuration": 600,
    },
    ORIGINAL: {
        "titles": [{"title": "Original title stays", "original": True, "votes": 5, "locked": False}],
        "thumbnails": [{"timestamp": None, "original": True, "votes": 2, "locked": False}],
        "randomTime": 0.1,
        "videoDuration": 100,
    },
    DOWNVOTED: {
        "titles": [{"title": "Should not appear", "original": False, "votes": -1, "locked": False}],
        "thumbnails": [],
        "randomTime": 0.5,
        "videoDuration": 50,
    },
    RUNS: {
        "titles": [{"title": "Calm runs title", "original": False, "votes": 0, "locked": True}],
        "thumbnails": [],
        "randomTime": 0.5,
        "videoDuration": 50,
    },
}

SEGMENTS = [
    {"category": "sponsor", "actionType": "skip", "segment": [10.0, 25.0], "UUID": "a", "votes": 4, "locked": 0},
    {"category": "intro", "actionType": "skip", "segment": [0.0, 5.0], "UUID": "b", "votes": 2, "locked": 0},
]

PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>Leanback stand-in</title></head>
<body>
<video id="player" muted></video>
<script>
const commands = [];
window._yttv = { app: { instance: { resolveCommand(command) { commands.push(command); return 'native:' + Object.keys(command)[0]; } } } };

(async () => {
  const exitMode = new URLSearchParams(location.search).get('exit') || 'leanback';
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const post = (path, body) => fetch(path, { method: 'POST', body: JSON.stringify(body) });
  const keys = [];
  const violations = [];
  document.addEventListener('keydown', (event) => keys.push(['down', event.keyCode]));
  document.addEventListener('keyup', (event) => keys.push(['up', event.keyCode]));
  document.addEventListener('securitypolicyviolation', (event) => violations.push(event.blockedURI));

  const result = {
    exitMode,
    companion: typeof window.__steamosYt === 'object',
    config: window.__steamosYt ? window.__steamosYt.config : null,
    userAgent: navigator.userAgent,
    uaData: null,
    mse: {
      vp9: MediaSource.isTypeSupported('video/webm; codecs="vp9"'),
      vp9At1080p60: MediaSource.isTypeSupported('video/webm; codecs="vp9"; width=1920; height=1080; framerate=60'),
      vp9AbsurdFramerate: MediaSource.isTypeSupported('video/webm; codecs="vp9"; framerate=9999'),
      vp9AbsurdWidth: MediaSource.isTypeSupported('video/webm; codecs="vp9"; width=99999'),
      hdrOnSdrDisplay: MediaSource.isTypeSupported('video/webm; codecs="vp09.02.51.10.01.09.16.09.00"; eotf=smpte2084'),
    },
  };
  if (navigator.userAgentData) {
    result.uaData = {
      brands: navigator.userAgentData.brands,
      platform: navigator.userAgentData.platform,
      high: await navigator.userAgentData.getHighEntropyValues(['architecture', 'fullVersionList', 'model']),
    };
  }

  window.dispatchEvent(new WheelEvent('wheel', { deltaY: 120, cancelable: true }));
  await sleep(150);
  result.wheelKeys = keys.splice(0);
  result.cursorHidden = document.documentElement.hasAttribute('data-steamos-yt-cursor-hidden');

  const buttons = Array.from({ length: 17 }, () => ({ pressed: false, touched: false, value: 0 }));
  const axes = [0, 0, 0, 0];
  const pad = { index: 0, id: 'Steam Virtual Gamepad (STANDARD GAMEPAD Vendor: 28de Product: 11ff)', connected: true, mapping: 'standard', buttons, axes, timestamp: 0 };
  Navigator.prototype.getGamepads = () => [pad, null, null, null];
  document.hasFocus = () => true;
  const press = (index, pressed) => { buttons[index] = { pressed, touched: pressed, value: pressed ? 1 : 0 }; };

  press(0, true); await sleep(120); press(0, false); await sleep(120);
  result.tapA = keys.splice(0);
  press(13, true); await sleep(800); press(13, false); await sleep(120);
  result.holdDown = keys.splice(0);
  axes[1] = -0.9; await sleep(120); axes[1] = 0; await sleep(120);
  result.stickUp = keys.splice(0);
  result.headers = await (await fetch('/headers')).json();

  const xhrJson = (path, style) => new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', path);
    const done = () => {
      try { resolve(JSON.parse(xhr.responseText)); } catch (error) { reject(error); }
    };
    if (style === 'listener') {
      xhr.addEventListener('load', done);
    } else {
      xhr.onreadystatechange = () => { if (xhr.readyState === 4) done(); };
    }
    xhr.onerror = () => reject(new Error('xhr failed ' + path));
    xhr.send('{}');
  });
  const browse = await xhrJson('/youtubei/v1/browse?prettyPrint=false', 'listener');
  const tiles = browse.contents.tvBrowseRenderer.content.tvSurfaceContentRenderer.content.sectionListRenderer.contents[0]
    .shelfRenderer.content.horizontalListRenderer.items.map((item) => item.tileRenderer);
  result.deArrow = tiles.map((tile) => ({
    id: tile.contentId,
    title: tile.metadata.tileMetadataRenderer.title.simpleText ?? tile.metadata.tileMetadataRenderer.title.runs.map((run) => run.text).join(''),
    thumbnails: tile.header.tileHeaderRenderer.thumbnail.thumbnails.map((thumbnail) => thumbnail.url),
  }));
  const next = await xhrJson('/youtubei/v1/next', 'property');
  const like = next.transportControls.transportControlsRenderer.engagementActions[0].button.likeButtonRenderer;
  const factoids = next.engagementPanels[0].engagementPanelSectionListRenderer.content.structuredDescriptionContentRenderer
    .items[0].videoDescriptionHeaderRenderer.factoid;
  result.dislikes = {
    button: like.dislikeCountText && like.dislikeCountText.simpleText,
    factoids: factoids.map((factoid) => [factoid.factoidRenderer.label.simpleText, factoid.factoidRenderer.value.simpleText]),
  };
  result.passthrough = await xhrJson('/headers', 'listener').then((headers) => typeof headers['user-agent'] === 'string', () => false);

  result.thumbnailLoads = await new Promise((resolve) => {
    const image = new Image();
    image.onload = () => resolve(true);
    image.onerror = () => resolve(false);
    image.src = 'https://dearrow-thumb.ajay.app/api/v1/getThumbnail?videoID=__SKIPPED__&time=42.5';
  });

  const video = document.getElementById('player');
  location.hash = '#/watch?v=__SKIPPED__';
  await sleep(1200);
  video.currentTime = 10.5;
  video.dispatchEvent(new Event('timeupdate'));
  await sleep(50);
  const afterSkip = video.currentTime;
  video.currentTime = 15;
  video.dispatchEvent(new Event('timeupdate'));
  await sleep(50);
  result.sponsorBlock = {
    afterSkip,
    midSegment: video.currentTime,
    toasts: commands.filter((command) => command.openPopupAction).map((command) => command.openPopupAction.popup.overlayToastRenderer.subtitle.simpleText),
  };
  result.cspViolations = violations;
  await post('/report', result);

  if (exitMode === 'combo') {
    press(8, true); press(9, true);
  } else if (exitMode === 'close') {
    window.close();
  } else {
    const instance = window._yttv.app.instance;
    await post('/report-hook', { wrapped: Boolean(instance.resolveCommand.__steamosYt), passthrough: instance.resolveCommand({ browseEndpoint: {} }) });
    instance.resolveCommand({ commandExecutorCommand: { commands: [{ signalAction: { signal: 'EXIT_APP' } }] } });
  }
})().catch((error) => fetch('/report-error', { method: 'POST', body: String(error && error.stack || error) }));
</script>
</body></html>
""".replace("__SKIPPED__", SKIPPED)


class Handler(BaseHTTPRequestHandler):
    output: Path

    def log_message(self, fmt, *args):
        pass

    def _headers(self):
        return {key.lower(): value for key, value in self.headers.items()}

    def _send(self, status, body=b"", content_type="text/plain", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, value, status=200):
        self._send(status, json.dumps(value).encode(), "application/json")

    def _log_api(self, url):
        with (self.output / "api.log").open("a") as log:
            log.write(f"{self.headers.get('Host')} {url.path}?{url.query}\n")

    def do_GET(self):
        url = urlsplit(self.path)
        host = (self.headers.get("Host") or "").split(":")[0]
        query = parse_qs(url.query)
        if host == "sponsor.ajay.app":
            self._log_api(url)
            if url.path.startswith("/api/skipSegments/"):
                wanted = json.loads(query.get("categories", ["[]"])[0])
                segments = [segment for segment in SEGMENTS if segment["category"] in wanted]
                return self._json([{"videoID": SKIPPED, "hash": "x", "segments": segments}] if segments else [], 200 if segments else 404)
            if url.path.startswith("/api/branding/"):
                return self._json(BRANDING)
            return self._send(404)
        if host == "returnyoutubedislikeapi.com":
            self._log_api(url)
            if url.path == "/votes" and query.get("videoId") == [SKIPPED]:
                return self._json({"id": SKIPPED, "likes": 10000, "dislikes": 1234})
            return self._send(404)
        if host == "dearrow-thumb.ajay.app":
            self._log_api(url)
            return self._send(200, PIXEL, "image/png")
        if url.path.startswith("/tv"):
            (self.output / "page-headers.json").write_text(json.dumps(self._headers(), indent=2))
            extra = {"Content-Security-Policy": "img-src 'self' https://i.ytimg.com; connect-src 'self'"}
            if query.get("probe"):
                extra["Set-Cookie"] = f"probe={query['probe'][0]}; Path=/; Max-Age=3600; SameSite=Lax"
            return self._send(200, PAGE.encode(), "text/html; charset=utf-8", extra)
        if url.path == "/headers":
            return self._json(self._headers())
        return self._send(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        path = urlsplit(self.path).path
        if path == "/youtubei/v1/browse":
            return self._json(BROWSE)
        if path == "/youtubei/v1/next":
            return self._json(NEXT)
        if path == "/headers":
            return self._json(self._headers())
        names = {"/report": "report.json", "/report-hook": "hook.json", "/report-error": "error.txt"}
        if path in names:
            (self.output / names[path]).write_bytes(body)
            return self._send(204)
        return self._send(404)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--cert", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    Handler.output = Path(args.output)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(args.cert, args.key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print("ready", flush=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Event().wait()


if __name__ == "__main__":
    main()
