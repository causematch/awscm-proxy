import socketserver
import sys
import urllib.request
from http.server import SimpleHTTPRequestHandler


def main():
    upstream = sys.argv[1]
    port = int(sys.argv[2])

    class Proxy(SimpleHTTPRequestHandler):
        def do_GET(self):
            url = f"{upstream}{self.path}"
            with urllib.request.urlopen(url) as ures:
                self.send_response(ures.status)
                for key, val in ures.headers.items():
                    self.send_header(key, val)
                self.end_headers()
                self.copyfile(ures, self.wfile)

    with socketserver.TCPServer(("localhost", port), Proxy) as httpd:
        print(f"serving at port {port}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
