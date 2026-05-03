import os
import socket
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import ssl

PORT = int(os.environ.get("PORT", 8080))

class ProxyHandler(BaseHTTPRequestHandler):
    log_message = lambda *args: None  # silence default logging

    def do_CONNECT(self):
        """Handle HTTPS tunneling."""
        try:
            host, port = self.path.split(":")
            port = int(port)
        except Exception:
            self.send_error(400, "Bad CONNECT request")
            return

        try:
            remote = socket.create_connection((host, port), timeout=10)
        except Exception:
            self.send_error(502, "Could not connect to target")
            return

        self.send_response(200, "Connection Established")
        self.end_headers()

        client = self.connection
        self._relay(client, remote)

    def do_GET(self):
        self._forward_request()

    def do_POST(self):
        self._forward_request()

    def do_PUT(self):
        self._forward_request()

    def do_DELETE(self):
        self._forward_request()

    def do_HEAD(self):
        self._forward_request()

    def do_OPTIONS(self):
        self._forward_request()

    def _forward_request(self):
        """Forward plain HTTP requests."""
        url = self.path
        if not url.startswith("http"):
            self.send_error(400, "Only absolute URLs supported")
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else None

        req = urllib.request.Request(
            url,
            data=body,
            method=self.command,
            headers={k: v for k, v in self.headers.items()
                     if k.lower() not in ("host", "proxy-connection", "connection")}
        )

        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in ("transfer-encoding",):
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_error(502, f"Upstream error: {e}")

    def _relay(self, client, remote):
        """Bidirectional raw TCP relay for CONNECT tunnels."""
        def forward(src, dst):
            try:
                while True:
                    data = src.recv(4096)
                    if not data:
                        break
                    dst.sendall(data)
            except Exception:
                pass
            finally:
                try: src.shutdown(socket.SHUT_RD)
                except: pass
                try: dst.shutdown(socket.SHUT_WR)
                except: pass

        t1 = threading.Thread(target=forward, args=(client, remote), daemon=True)
        t2 = threading.Thread(target=forward, args=(remote, client), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), ProxyHandler)
    print(f"[*] Proxy listening on 0.0.0.0:{PORT}")
    server.serve_forever()
