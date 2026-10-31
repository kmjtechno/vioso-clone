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
from .script import ScriptError, parse_env, run_script

_NEEDS_HARDWARE = "ERR not supported by clone (needs hardware)"


class RemoteController:
    def __init__(self, project=None, base_dir="."):
        self.project = project
        self.base_dir = Path(base_dir)
        self._lock = threading.Lock()
        self._running = False

    def _safe(self, name):
        root = self.base_dir.resolve()
        p = (root / name).resolve()
        if p != root and root not in p.parents:
            raise ValueError("path outside working directory")
        return p

    def handle(self, line):
        line = line.strip()
        parts = line.split(None, 1)
        if not parts:
            return "ERR empty command"
        with self._lock:
            try:
                if ".htm" in parts[0]:
                    return self._url_dispatch(parts[0])
                cmd, arg = parts[0].upper(), (parts[1].strip() if len(parts) > 1 else "")
                return self._dispatch(cmd, arg)
            except (MissingInput, ValueError, OSError, KeyError, TypeError, NotImplementedStep, ScriptError) as e:
                return f"ERR {e}"

    def _url_dispatch(self, target):
        """URL-style commands: page.htm?key=value&key2=..., as in the original's remote interface."""
        u = urlparse(target)
        page = u.path.lstrip("/").lower()
        q = parse_qs(u.query, keep_blank_values=True)
        if page == "control.htm":
            if "save" in q:
                if self.project is None:
                    return "ERR no project"
                self.project.save(self._safe(q["save"][0]))
                return "OK saved"
            return _NEEDS_HARDWARE if q else "ERR missing command"
        if page == "script.htm":
            if "status" in q:
                return "OK running" if self._running else "OK idle"
            if "abort" in q:
                return "OK nothing running"
            if "execute" in q:
                f = self._safe(q["execute"][0])
                if not f.is_file():
                    return f"ERR file not found: {q['execute'][0]}"
                env = parse_env(";".join(q.get("param", [])))
                self._running = True
                try:
                    ctx = run_script(f.read_text(encoding="utf-8"), env=env, project=self.project,
                                     base_dir=self.base_dir)
                finally:
                    self._running = False
                self.project = ctx.project
                return "OK executed"
            return "ERR unknown script command"
        if page in ("info.htm", "model3d.htm"):
            return _NEEDS_HARDWARE
        return f"ERR unknown page {page}"

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
                    line = raw.decode("utf-8", "replace")
                    if line.startswith("GET "):
                        return self._http(line)
                    self.wfile.write((ctl.handle(line) + "\n").encode())

            def _http(self, request_line):
                for hdr in self.rfile:  # consume headers up to the blank line
                    if not hdr.strip():
                        break
                bits = request_line.split()
                reply = ctl.handle(bits[1].lstrip("/")) if len(bits) > 1 else "ERR bad request"
                body = (reply + "\n").encode()
                status = "200 OK" if reply.startswith("OK") else "400 Bad Request"
                self.wfile.write(f"HTTP/1.1 {status}\r\nContent-Type: text/plain; charset=utf-8\r\n"
                                 f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)

        class Udp(socketserver.BaseRequestHandler):
            def handle(self):
                ctl.handle(self.request[0].decode("utf-8", "replace"))  # fire-and-forget: no reply

        class Http(BaseHTTPRequestHandler):
            def do_GET(self):
                u = urlparse(self.path)
                if u.path.endswith(".htm") and u.path != "/control.htm" or (u.path == "/control.htm" and "cmd" not in u.query):
                    reply = ctl.handle(self.path.lstrip("/"))
                elif u.path == "/control.htm":
                    reply = ctl.handle(parse_qs(u.query).get("cmd", [""])[0])
                else:
                    return self._send(404, "ERR not found")
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
