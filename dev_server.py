"""Lightweight dev server for local preview.

Mimics Vercel's `cleanUrls: true` behavior: when a request path doesn't
resolve to a file, try the same path with a `.html` extension appended
before returning 404. Matches what Vercel does in production so the
preview matches deployed behavior.
"""
import http.server
import os
import posixpath
import sys
from urllib.parse import urlsplit, urlunsplit


class CleanUrlHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        resolved = super().translate_path(path)
        # If the requested path exists as-is (file or directory), serve it.
        if os.path.exists(resolved):
            return resolved
        # If adding .html makes it a real file, rewrite to that.
        html_candidate = resolved.rstrip("/") + ".html"
        if os.path.isfile(html_candidate):
            return html_candidate
        return resolved


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = http.server.ThreadingHTTPServer(("", port), CleanUrlHandler)
    print(f"Serving with clean URLs on http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
