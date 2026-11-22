"""
MCP server (stdio) exposing a KiCad project to Claude Code, Claude Desktop, Antigravity or any
other MCP client. The client's model brings the conversation and web search (part availability,
datasheets); this server supplies the design: parts, fields, pin-to-net connectivity and Irona's
checks, review and simulation.

    python3 -m irona mcp [--project DIR]

Standard library only. Messages are newline-delimited JSON-RPC 2.0 on stdin/stdout; logs go to
stderr so they never corrupt the protocol stream.
"""

import contextlib
import json
import logging
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

from irona import __version__
from irona.assistant_tools import TOOLS, ToolError, Workspace, call, to_json

logger = logging.getLogger("irona.mcp")

SUPPORTED_PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

INSTRUCTIONS = (
    "Irona reads KiCad projects from disk (save in KiCad first). Use get_design_overview to see the parts "
    "and nets, get_component for pin-level connectivity, and run_rule_check / run_design_review / "
    "run_simulation for Irona's analyses. For availability, pricing, lifecycle and datasheet values, use your "
    "own web search and cite the sources; the project only stores what the designer entered."
)


class MCPServer:
    def __init__(self, default_project: Optional[Path] = None, search_root: Optional[Path] = None):
        self.ws = Workspace(default_project, search_root)

    def tool_list(self):
        return [{"name": t["name"], "description": t["description"], "inputSchema": t["input_schema"]} for t in TOOLS]

    def handle(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Returns the JSON-RPC response for a request, or None for notifications."""
        method, msg_id, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
        if msg_id is None:  # notification (initialized, cancelled, …)
            return None
        try:
            if method == "initialize":
                asked = params.get("protocolVersion")
                result = {
                    "protocolVersion": asked if asked in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0],
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "irona", "title": "Irona for KiCad", "version": __version__},
                    "instructions": INSTRUCTIONS,
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.tool_list()}
            elif method == "tools/call":
                result = self.call_tool(params.get("name", ""), params.get("arguments") or {})
            elif method in ("resources/list", "prompts/list"):
                result = {method.split("/")[0]: []}
            else:
                return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
        except Exception as e:  # never let one request kill the server
            logger.error(traceback.format_exc())
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32603, "message": str(e)}}
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Analysis code must not write to stdout: that is the protocol channel.
            with contextlib.redirect_stdout(sys.stderr):
                data = call(self.ws, name, arguments)
            return {"content": [{"type": "text", "text": to_json(data)}], "isError": False}
        except ToolError as e:
            return {"content": [{"type": "text", "text": str(e)}], "isError": True}
        except Exception as e:
            logger.error(traceback.format_exc())
            return {"content": [{"type": "text", "text": f"{name} failed: {e}"}], "isError": True}

    def serve(self, stdin=None, stdout=None) -> None:
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
            else:
                if isinstance(msg, list):  # batch (older protocol revisions)
                    replies = [r for r in (self.handle(m) for m in msg if isinstance(m, dict)) if r]
                    reply = replies or None
                elif isinstance(msg, dict):
                    reply = self.handle(msg)
                else:
                    reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}}
            if reply is not None:
                stdout.write(json.dumps(reply) + "\n")
                stdout.flush()


def _is_project(d: Path) -> bool:
    return d.is_dir() and (any(d.glob("*.kicad_pcb")) or any(d.glob("*.kicad_sch")))


def main(project: Optional[str] = None) -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="irona-mcp: %(message)s")
    start = Path(project).expanduser().resolve() if project else Path.cwd()
    # A folder that is not itself a KiCad project (e.g. an editor workspace) is only a search root.
    default = start if _is_project(start) else None
    logger.info("serving %s", default or f"(no default project; tools take `project`, search root {start})")
    MCPServer(default, search_root=start).serve()
    return 0
