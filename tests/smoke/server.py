#!/usr/bin/env python3
"""HTTPS stand-in for www.youtube.com/tv used by the smoke test.

It serves a page that inspects what the companion extension changed, posts the
findings back, and then asks the kiosk to exit through one of the supported
paths (Leanback's EXIT_APP command, the controller combo or window.close).
"""

import argparse
import json
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>Leanback stand-in</title></head>
<body>
<script>
(async () => {
  const exitMode = new URLSearchParams(location.search).get('exit') || 'leanback';
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const post = (path, body) => fetch(path, { method: 'POST', body: JSON.stringify(body) });
  const keys = [];
  document.addEventListener('keydown', (event) => keys.push(['down', event.keyCode]));
  document.addEventListener('keyup', (event) => keys.push(['up', event.keyCode]));

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
  await post('/report', result);

  if (exitMode === 'combo') {
    press(8, true); press(9, true);
  } else if (exitMode === 'close') {
    window.close();
  } else {
    window._yttv = { app: { instance: { resolveCommand(command) { return 'native:' + Object.keys(command)[0]; } } } };
    await sleep(700);
    const instance = window._yttv.app.instance;
    await post('/report-hook', { wrapped: Boolean(instance.resolveCommand.__steamosYt), passthrough: instance.resolveCommand({ browseEndpoint: {} }) });
    instance.resolveCommand({ commandExecutorCommand: { commands: [{ signalAction: { signal: 'EXIT_APP' } }] } });
  }
})().catch((error) => fetch('/report-error', { method: 'POST', body: String(error && error.stack || error) }));
</script>
</body></html>
"""


class Handler(BaseHTTPRequestHandler):
    output: Path

    def log_message(self, fmt, *args):
        pass

    def _headers(self):
        return {key.lower(): value for key, value in self.headers.items()}

    def _send(self, status, body=b"", content_type="text/plain"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/tv"):
            (self.output / "page-headers.json").write_text(json.dumps(self._headers(), indent=2))
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif self.path == "/headers":
            self._send(200, json.dumps(self._headers()).encode(), "application/json")
        else:
            self._send(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        names = {"/report": "report.json", "/report-hook": "hook.json", "/report-error": "error.txt"}
        if self.path in names:
            (self.output / names[self.path]).write_bytes(body)
            self._send(204)
        else:
            self._send(404)


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
