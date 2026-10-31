"""Remote control: one command set served over TCP (lines), UDP (datagrams) and HTTP.

The wire protocol is the clone's own (PING, STATUS, LOAD, SAVE, STEP); it is not the
original application's protocol. Servers bind to loopback unless a host is given.
"""
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .project import MissingInput, NotImplementedStep, Project, run_step


class RemoteController:
    def __init__(self, project=None, base_dir="."):
        self.project = project
        self.base_dir = Path(base_dir)
        self._lock = threading.Lock()

    def _safe(self, name):
        root = self.base_dir.resolve()
        p = (root / name).resolve()
        if p != root and root not in p.parents:
            raise ValueError("path outside working directory")
        return p

    def handle(self, line):
        parts = line.strip().split(None, 1)
        if not parts:
            return "ERR empty command"
        cmd, arg = parts[0].upper(), (parts[1].strip() if len(parts) > 1 else "")
        with self._lock:
            try:
                return self._dispatch(cmd, arg)
            except (MissingInput, ValueError, OSError, KeyError, TypeError, NotImplementedStep) as e:
                return f"ERR {e}"

    def _dispatch(self, cmd, arg):
        if cmd == "PING":
            return "OK pong"
        if cmd == "STATUS":
            p = self.project
            return "OK " + ("no project" if p is None else f"{p.name} steps={','.join(p.steps_done) or '-'}")
        if cmd in ("LOAD", "SAVE", "STEP") and not arg:
            return f"ERR {cmd} needs an argument"
        if cmd == "LOAD":
            f = self._safe(arg)
            if not f.is_file():
                return f"ERR file not found: {arg}"
            self.project = Project.load(f)
            return "OK loaded"
        if cmd == "SAVE":
            if self.project is None:
                return "ERR no project"
            self.project.save(self._safe(arg))
            return "OK saved"
        if cmd == "STEP":
            if self.project is None:
                return "ERR no project"
            run_step(self.project, arg)
            return f"OK {arg} done"
        return f"ERR unknown command {cmd}"


class RemoteServer:
    def __init__(self, controller, host="127.0.0.1", tcp_port=0, udp_port=0, http_port=0):
        self.controller, self.host = controller, host
        self._ports = (tcp_port, udp_port, http_port)
        self._servers = []
        self.tcp_port = self.udp_port = self.http_port = None

    def start(self):
        ctl = self.controller

        class Tcp(socketserver.StreamRequestHandler):
            def handle(self):
                for raw in self.rfile:
                    self.wfile.write((ctl.handle(raw.decode("utf-8", "replace")) + "\n").encode())

        class Udp(socketserver.BaseRequestHandler):
            def handle(self):
                data, sock = self.request
                sock.sendto((ctl.handle(data.decode("utf-8", "replace")) + "\n").encode(), self.client_address)

        class Http(BaseHTTPRequestHandler):
            def do_GET(self):
                u = urlparse(self.path)
                if u.path != "/control.htm":
                    return self._send(404, "ERR not found")
                reply = ctl.handle(parse_qs(u.query).get("cmd", [""])[0])
                self._send(200 if reply.startswith("OK") else 400, reply)

            def _send(self, code, text):
                body = (text + "\n").encode()
                self.send_response(code)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        class TcpS(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = True

        tcp = TcpS((self.host, self._ports[0]), Tcp)
        udp = socketserver.ThreadingUDPServer((self.host, self._ports[1]), Udp)
        http = ThreadingHTTPServer((self.host, self._ports[2]), Http)
        self._servers = [tcp, udp, http]
        self.tcp_port, self.udp_port, self.http_port = (s.server_address[1] for s in self._servers)
        for s in self._servers:
            s.daemon_threads = True
            threading.Thread(target=s.serve_forever, daemon=True).start()

    def stop(self):
        for s in self._servers:
            s.shutdown()
            s.server_close()
        self._servers = []
