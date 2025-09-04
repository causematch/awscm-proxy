import socketserver
import sys
from io import StringIO


class MyTCPHandler(socketserver.BaseRequestHandler):
    """
    The RequestHandler class for our server.

    It is instantiated once per connection to the server, and must
    override the handle() method to implement communication to the
    client.
    """

    def handle(self):
        # self.request is the TCP socket connected to the client
        request = StringIO()
        data = self.request.recv(1024).decode()
        print(data)
        request.write(data)
        rlen = request.tell()
        self.request.send(
            b"HTTP/1.1 200 OK\nX-tra: header\nContent-Type: text/plain\nContent-Length: %d\n\n%s"
            % (rlen, request.getvalue().encode())
        )
        self.request.close()


def run(port=0, address="localhost"):
    if address.startswith("unix:"):
        port = address.split(":")[1]
        server = socketserver.UnixStreamServer(port, MyTCPHandler)
        sa = server.socket.getsockname()
        print("Serving HTTP on %s" % sa)
    else:
        port = int(port)
        server = socketserver.TCPServer((address, port), MyTCPHandler)
        sa = server.socket.getsockname()
        print("Serving HTTP on %s:%d" % sa)
    yield sa

    # Activate the server; this will keep running until you
    # interrupt the program with Ctrl-C
    server.serve_forever()
    # server.handle_request()


if __name__ == "__main__":
    for p in run(*reversed(sys.argv[1:])):
        pass
