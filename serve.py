"Local web server."

import http.server
import socketserver

PORT = 8002

Handler = http.server.SimpleHTTPRequestHandler

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"serving HTML at http://localhost:{PORT}/library")
    httpd.serve_forever()
