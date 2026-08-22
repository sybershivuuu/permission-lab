import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
CAPTURES = ROOT / "captures"
CAPTURES.mkdir(exist_ok=True)

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/":
            data = (ROOT / "index.html").read_bytes()

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_error(404)

    def do_POST(self):
        if self.path != "/capture":
            self.send_error(404)
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

        filename = CAPTURES / f"capture-{time.time_ns()}.jpg"
        filename.write_bytes(photo)

        print(f"[+] Saved: {filename.name}")

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"saved")

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")


server = ThreadingHTTPServer((os.getenv("HOST", "0.0.0.0"), int(os.getenv("PORT", "8080"))), Handler)

print("Serving lab on http://127.0.0.1:8080/")
print("Captures:", CAPTURES)

server.serve_forever()
