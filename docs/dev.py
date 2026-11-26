"""Live preview: rebuild the site when a source file changes, and reload the page.

    uv run python docs/dev.py      # http://localhost:8000/

The server serves the built site (``site/``) at the root, exactly as GitHub Pages
does. The alignment checker is served from ``/tools/audit.html``. Every HTML
response gets a small reload client, which polls ``/__build``; when a rebuild
bumps the stamp the page reloads itself. Assets are served with ``no-store`` so a
reload always shows the current CSS.

Only the build's sources are watched — ``content/``, ``theme/``, ``pipeline/``,
``nav.py`` and ``build.py``. A rebuild takes well under a second.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import posixpath
import sys
import threading
import time
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import build  # noqa: E402  (after sys.path)

WATCH = (
    HERE / "content",
    HERE / "theme",
    HERE / "pipeline",
    HERE / "nav.py",
    HERE / "build.py",
)

SITE = ROOT / "site"

RELOAD = """<script>
(() => {
  let stamp = null;
  const tick = async () => {
    try {
      const response = await fetch("/__build", { cache: "no-store" });
      const next = await response.text();
      if (stamp === null) stamp = next;
      else if (next !== stamp) location.reload();
    } catch (_) {}
  };
  setInterval(tick, 700);
})();
</script>"""

_state = {"stamp": "0", "lock": threading.Lock()}


def _mtimes() -> dict[str, float]:
    seen: dict[str, float] = {}
    for path in WATCH:
        if path.is_file():
            seen[str(path)] = path.stat().st_mtime
        elif path.is_dir():
            for item in path.rglob("*"):
                if item.suffix in {".md", ".py", ".css", ".js", ".svg", ".json"}:
                    seen[str(item)] = item.stat().st_mtime
    return seen


def _rebuild() -> None:
    with _state["lock"]:
        started = time.time()
        try:
            code = build.main()
        except (
            Exception
        ) as error:  # keep the server alive; the traceback is the message
            print(f"\n  build failed: {error}", flush=True)
            code = 1
        if code == 0:
            _state["stamp"] = str(time.time_ns())
            print(f"  rebuilt in {time.time() - started:.2f}s", flush=True)
        else:
            print("  build reported a problem; page left as it was", flush=True)


def _watch() -> None:
    seen = _mtimes()
    while True:
        time.sleep(0.4)
        now = _mtimes()
        if now != seen:
            seen = now
            _rebuild()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        if self.path.split("?")[0] == "/__build":
            body = _state["stamp"].encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def translate_path(self, path: str) -> str:
        """Serve the built site at the root; the checker comes from the sources."""
        clean = unquote(path.split("?", 1)[0].split("#", 1)[0], errors="surrogatepass")
        if clean == "/tools" or clean.startswith("/tools/"):
            return str(HERE / posixpath.normpath(clean).lstrip("/"))
        return str(SITE / posixpath.normpath(clean).lstrip("/"))

    def send_head(self):  # type: ignore[no-untyped-def]
        file = Path(self.translate_path(self.path))
        if file.is_dir():
            file = file / "index.html"
        if file.suffix == ".html" and file.is_file():
            try:
                text = file.read_text(encoding="utf-8")
            except OSError:
                return super().send_head()
            text = text.replace("</body>", RELOAD + "\n</body>", 1)
            body = text.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            import io

            return io.BytesIO(body)
        return super().send_head()

    def log_message(self, fmt: str, *args: object) -> None:
        if args and str(args[0]).startswith(("GET /__build", "GET /assets")):
            return
        super().log_message(fmt, *args)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild the documentation website on change and serve it."
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--no-build", action="store_true", help="serve without the first rebuild"
    )
    args = parser.parse_args()

    if not args.no_build:
        _rebuild()
    threading.Thread(target=_watch, daemon=True).start()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler))
    print(
        json.dumps(
            {
                "site": f"http://localhost:{args.port}/",
                "audit": (
                    f"http://localhost:{args.port}/tools/audit.html?page=/quickstart/"
                ),
            },
            indent=2,
        ),
        flush=True,
    )
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
