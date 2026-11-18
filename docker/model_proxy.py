#!/usr/bin/env python3
"""Loopback OpenAI-compatible proxy: inject Bearer token and forward to a remote LM Studio.

Lastbook only calls http://127.0.0.1:<port>/v1/... and never sends Authorization.
This process listens on loopback, adds the token, and streams to LMSTUDIO_URL.
"""
from __future__ import annotations

import http.client
import http.server
import os
import sys
import urllib.parse


def _require_env(name: str) -> str:
    value = os.environ.get(name, '').strip()
    if not value:
        sys.exit(f'{name} is required')
    return value


LISTEN_HOST = '127.0.0.1'
LISTEN_PORT = int(os.environ.get('MODEL_PROXY_PORT', '19443'))
UPSTREAM = urllib.parse.urlparse(_require_env('LMSTUDIO_URL'))
TOKEN = _require_env('LMSTUDIO_TOKEN')

if UPSTREAM.scheme not in ('http', 'https') or not UPSTREAM.hostname:
    sys.exit('LMSTUDIO_URL must be http(s)://host[:port]')

UP_HOST = UPSTREAM.hostname
UP_PORT = UPSTREAM.port or (443 if UPSTREAM.scheme == 'https' else 80)
UP_PREFIX = UPSTREAM.path.rstrip('/')  # usually empty; keep if user put a path prefix
HOP_BY_HOP = {
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailers', 'transfer-encoding', 'upgrade', 'proxy-connection',
}


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        sys.stderr.write('model-proxy: %s\n' % (fmt % args))

    def do_GET(self):
        self._proxy()

    def do_POST(self):
        self._proxy()

    def do_PUT(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def do_OPTIONS(self):
        self._proxy()

    def do_HEAD(self):
        self._proxy()

    def _read_body(self) -> bytes:
        length = int(self.headers.get('Content-Length', '0') or 0)
        if length <= 0:
            return b''
        return self.rfile.read(length)

    def _proxy(self):
        path = self.path
        if UP_PREFIX:
            path = UP_PREFIX + path
        body = self._read_body()
        headers = {}
        for key, value in self.headers.items():
            lk = key.lower()
            if lk in HOP_BY_HOP or lk == 'host' or lk == 'authorization':
                continue
            headers[key] = value
        headers['Host'] = f'{UP_HOST}:{UP_PORT}' if UP_PORT not in (80, 443) else UP_HOST
        headers['Authorization'] = f'Bearer {TOKEN}'
        headers['Connection'] = 'close'
        if body and 'Content-Length' not in headers:
            headers['Content-Length'] = str(len(body))

        try:
            if UPSTREAM.scheme == 'https':
                conn = http.client.HTTPSConnection(UP_HOST, UP_PORT, timeout=300)
            else:
                conn = http.client.HTTPConnection(UP_HOST, UP_PORT, timeout=300)
            conn.request(self.command, path, body=body or None, headers=headers)
            upstream = conn.getresponse()
        except OSError as e:
            self.send_error(502, f'upstream unreachable: {e}')
            return

        self.send_response(upstream.status, upstream.reason)
        for key, value in upstream.getheaders():
            if key.lower() in HOP_BY_HOP:
                continue
            self.send_header(key, value)
        self.send_header('Connection', 'close')
        self.end_headers()
        if self.command == 'HEAD':
            conn.close()
            return
        try:
            while True:
                chunk = upstream.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            conn.close()


class ThreadingHTTPServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    # Refuse binding anything but loopback.
    if LISTEN_HOST not in ('127.0.0.1', '::1'):
        sys.exit('MODEL_PROXY must listen on loopback only')
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    print(
        f'model-proxy listening on http://{LISTEN_HOST}:{LISTEN_PORT} -> '
        f'{UPSTREAM.scheme}://{UP_HOST}:{UP_PORT}{UP_PREFIX} (Bearer auth)',
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
