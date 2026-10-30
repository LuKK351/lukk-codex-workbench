#!/usr/bin/env python3
"""Serve only the five public workbench assets on loopback; never source/backups."""
import argparse
import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if urlsplit(self.path).path == '/__workbench_health':
            from launcher import identity
            root = Path(self.directory)
            config = json.loads((root / 'config/workbench.json').read_text(encoding='utf-8'))
            payload = json.dumps(dict(identity(root, config), pid=os.getpid())).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if urlsplit(self.path).path not in ('/', '/index.html', '/app.js', '/core.js', '/style.css', '/data.json'):
            self.send_error(404); return
        super().do_GET()

    def do_HEAD(self):
        if urlsplit(self.path).path not in ('/', '/index.html', '/app.js', '/core.js', '/style.css', '/data.json'):
            self.send_error(404); return
        super().do_HEAD()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root'); p.add_argument('--port', type=int, default=8770)
    args = p.parse_args()
    root = Path(args.root).resolve()
    if not (root / 'data.json').is_file(): p.error('目录中缺少 data.json')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(Handler, directory=str(root)))
    print(f'http://127.0.0.1:{server.server_address[1]}/', flush=True)
    server.serve_forever()
