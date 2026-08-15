"""
KiCad 10 IPC Server & Client Bridge (kicad-python)
Provides JSON-RPC socket communication with live KiCad 10 PCB Editor sessions.
Includes a MockKiCadIPCServer for headless CI/CD and testing environments.
"""

import os
import sys
import json
import time
import socket
import select
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("IPCBridge")


class KiCad10IPCClient:
    """
    Client interface connecting to KiCad 10 IPC socket.
    Exposes methods to inspect board, place footprints, route tracks, and trigger DRC.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 4242, socket_path: Optional[str] = "/tmp/kicad_ipc_socket"):
        self.host = host
        self.port = port
        self.socket_path = socket_path
        self.sock: Optional[socket.socket] = None
        self.is_connected = False

    def connect(self, timeout: float = 2.0) -> bool:
        """Attempts to connect to KiCad 10 via Unix socket or TCP."""
        # Try Unix Domain Socket first if available on Linux/macOS
        if self.socket_path and os.path.exists(self.socket_path):
            try:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.settimeout(timeout)
                self.sock.connect(self.socket_path)
                self.is_connected = True
                logger.info(f"Connected to KiCad 10 via Unix socket: {self.socket_path}")
                return True
            except Exception as e:
                logger.warning(f"Unix socket connection failed: {e}")
                if self.sock:
                    self.sock.close()
                    self.sock = None

        # Fallback to TCP socket
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(timeout)
            self.sock.connect((self.host, self.port))
            self.is_connected = True
            logger.info(f"Connected to KiCad 10 via TCP: {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.info(f"Live KiCad 10 IPC socket not available on {self.host}:{self.port} ({e})")
            if self.sock:
                self.sock.close()
                self.sock = None
            self.is_connected = False
            return False

    def send_rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send JSON-RPC request to KiCad 10 session."""
        if not self.is_connected or not self.sock:
            raise ConnectionError("Not connected to KiCad 10 IPC socket.")

        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": method,
            "params": params or {}
        }
        msg = json.dumps(payload) + "\n"
        self.sock.sendall(msg.encode("utf-8"))

        data = b""
        while not data.endswith(b"\n"):
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            data += chunk

        response = json.loads(data.decode("utf-8"))
        if "error" in response:
            raise RuntimeError(f"KiCad IPC Error: {response['error']}")
        return response.get("result", {})

    def ping(self) -> bool:
        """Check if KiCad 10 IPC is responding."""
        try:
            res = self.send_rpc("ping")
            return res.get("status") == "ok"
        except Exception:
            return False

    def place_footprint(self, ref: str, x: float, y: float, angle: float = 0.0, layer: str = "F.Cu") -> Dict[str, Any]:
        return self.send_rpc("place_footprint", {"ref": ref, "x": x, "y": y, "angle": angle, "layer": layer})

    def route_track(self, start_x: float, start_y: float, end_x: float, end_y: float, width: float, layer: str, net_name: str) -> Dict[str, Any]:
        return self.send_rpc("route_track", {
            "start": [start_x, start_y],
            "end": [end_x, end_y],
            "width": width,
            "layer": layer,
            "net": net_name
        })

    def add_via(self, x: float, y: float, size: float = 0.6, drill: float = 0.3, net_name: str = "") -> Dict[str, Any]:
        return self.send_rpc("add_via", {"x": x, "y": y, "size": size, "drill": drill, "net": net_name})

    def run_drc(self) -> Dict[str, Any]:
        return self.send_rpc("run_drc")

    def save_board(self, filepath: str) -> Dict[str, Any]:
        return self.send_rpc("save_board", {"path": filepath})

    def close(self) -> None:
        if self.sock:
            self.sock.close()
            self.is_connected = False


class MockKiCadIPCServer:
    """
    Mock KiCad 10 IPC Server for testing and CI/CD environments.
    Emulates the KiCad 10 JSON-RPC protocol in a background thread.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 4242):
        self.host = host
        self.port = port
        self.server_sock: Optional[socket.socket] = None
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.board_state: Dict[str, Any] = {
            "footprints": {},
            "tracks": [],
            "vias": [],
            "drc_violations": []
        }

    def start(self) -> None:
        """Start the mock server in a background daemon thread."""
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen(5)
        self.is_running = True
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()
        logger.info(f"Mock KiCad 10 IPC Server running on {self.host}:{self.port}")

    def _serve(self) -> None:
        while self.is_running:
            try:
                readable, _, _ = select.select([self.server_sock], [], [], 0.5)
                if readable:
                    conn, _ = self.server_sock.accept()
                    client_thread = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
                    client_thread.start()
            except Exception:
                break

    def _handle_client(self, conn: socket.socket) -> None:
        with conn:
            buffer = ""
            while self.is_running:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if not line.strip():
                        continue
                    try:
                        req = json.loads(line)
                        res = self._dispatch(req)
                        conn.sendall((json.dumps(res) + "\n").encode("utf-8"))
                    except Exception as e:
                        err_res = {"jsonrpc": "2.0", "error": str(e)}
                        conn.sendall((json.dumps(err_res) + "\n").encode("utf-8"))

    def _dispatch(self, req: Dict[str, Any]) -> Dict[str, Any]:
        req_id = req.get("id", 1)
        method = req.get("method")
        params = req.get("params", {})

        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"status": "ok", "version": "10.0-mock"}}

        elif method == "place_footprint":
            ref = params.get("ref")
            self.board_state["footprints"][ref] = params
            return {"jsonrpc": "2.0", "id": req_id, "result": {"placed": ref, "position": [params.get("x"), params.get("y")]}}

        elif method == "route_track":
            self.board_state["tracks"].append(params)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"routed": True, "track_count": len(self.board_state["tracks"])}}

        elif method == "add_via":
            self.board_state["vias"].append(params)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"added_via": True, "via_count": len(self.board_state["vias"])}}

        elif method == "run_drc":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "violations": self.board_state["drc_violations"],
                    "unconnected_items": 0,
                    "status": "PASS"
                }
            }

        elif method == "save_board":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"saved": True, "path": params.get("path")}}

        return {"jsonrpc": "2.0", "id": req_id, "error": f"Unknown method {method}"}

    def stop(self) -> None:
        self.is_running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass


if __name__ == "__main__":
    server = MockKiCadIPCServer()
    server.start()
    try:
        client = KiCad10IPCClient()
        if client.connect():
            print("Ping response:", client.ping())
            print("Place response:", client.place_footprint("U1", 30.0, 20.0))
            print("DRC response:", client.run_drc())
            client.close()
    finally:
        server.stop()
