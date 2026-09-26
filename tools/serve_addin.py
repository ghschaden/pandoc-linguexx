#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Gerhard Schaden
#
# This file is part of pandoc-linguexx.
#
# pandoc-linguexx is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# pandoc-linguexx is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Serve the Word add-in for development, over HTTPS on this machine.

    python3 tools/serve_addin.py                 # https://localhost:3000
    python3 tools/serve_addin.py --manifest-only --base https://example.org/lx

Office loads an add-in only over HTTPS, so this makes a self-signed
certificate for localhost once (in .addin-cert/, which git ignores) and
serves addin/ with it.  Nothing leaves this machine: Word -- desktop, or on
the web in this machine's browser -- fetches the pages from localhost.

The browser has to trust the certificate before Word's frame will load the
page: open https://localhost:3000/word/taskpane.html once and accept it.

It also writes addin/word/manifest.xml from manifest.template.xml with the
base URL filled in -- that is the file Word's "Upload My Add-in" wants.
--manifest-only writes it for another base and serves nothing.
"""

from __future__ import annotations

import argparse
import http.server
import shutil
import ssl
import subprocess
import sys
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADDIN = ROOT / "addin"
CERT_DIR = ROOT / ".addin-cert"
TEMPLATE = ADDIN / "word" / "manifest.template.xml"
MANIFEST = ADDIN / "word" / "manifest.xml"


def write_manifest(base: str) -> Path:
    base = base.rstrip("/")
    MANIFEST.write_text(TEMPLATE.read_text(encoding="utf-8").replace("{{BASE}}", base),
                        encoding="utf-8")
    return MANIFEST


def certificate() -> tuple[Path, Path]:
    cert, key = CERT_DIR / "cert.pem", CERT_DIR / "key.pem"
    if cert.is_file() and key.is_file():
        return cert, key
    if not shutil.which("openssl"):
        sys.exit("openssl is needed once, to make a certificate for localhost")
    CERT_DIR.mkdir(exist_ok=True)
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-keyout", str(key), "-out", str(cert), "-days", "825",
         "-subj", "/CN=localhost",
         "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
        check=True, capture_output=True)
    return cert, key


class Handler(http.server.SimpleHTTPRequestHandler):
    # ES modules are refused unless served as JavaScript.
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".js": "text/javascript", ".mjs": "text/javascript",
                      ".xml": "application/xml"}

    def end_headers(self) -> None:
        # a stale module after an edit is an afternoon lost
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=3000)
    ap.add_argument("--base", help="URL addin/ is served at (default https://localhost:PORT)")
    ap.add_argument("--manifest-only", action="store_true")
    args = ap.parse_args(argv)
    base = args.base or f"https://localhost:{args.port}"
    manifest = write_manifest(base)
    print(f"manifest: {manifest}  (base {base})")
    if args.manifest_only:
        return 0

    cert, key = certificate()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", args.port), partial(Handler, directory=str(ADDIN)))
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    print(f"serving {ADDIN} at {base}/  (Ctrl+C to stop)")
    print(f"1. open {base}/word/taskpane.html once and accept the certificate")
    print("2. in Word: Add-ins > More Add-ins > My Add-ins > Upload My Add-in,")
    print(f"   and choose {manifest}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
