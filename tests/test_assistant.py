import contextlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

from tests.helpers import ProjectTestCase

from irona import assistant as ai
from irona.assistant_tools import ToolError, Workspace, call, validate
from irona.design_context import DesignContext
from irona.mcp_server import MCPServer


class TestDesignContext(ProjectTestCase):
    def test_pins_nets_and_fields(self):
        ctx = DesignContext.load(self.project_dir)
        u1 = ctx.component_detail("u1")  # case-insensitive
        pins = {p["pad"]: p for p in u1["pins"]}
        self.assertEqual((pins["2"]["name"], pins["2"]["net"]), ("SW", "SW_NODE"))
        self.assertIn("L1.1", pins["2"]["connected_to"])
        self.assertEqual(pins["5"]["name"], "EN")
        fb = ctx.net_detail("FB")
        self.assertEqual(sorted(n["ref"] for n in fb["nodes"]), ["R1", "R2", "U1"])
        ov = ctx.overview()
        self.assertEqual(ov["component_count"], 11)
        self.assertIn("U1", ov["missing_mpn"])  # sample has no MPN fields

    def test_reads_mpn_and_datasheet_fields(self):
        sch = self.sch.read_text()
        sch = sch.replace('(property "Value" "TPS54202"',
                          '(property "MPN" "TPS54202DDCR" (at 0 0 0))\n    (property "Manufacturer" "Texas Instruments" (at 0 0 0))\n'
                          '    (property "Datasheet" "https://www.ti.com/lit/ds/symlink/tps54202.pdf" (at 0 0 0))\n    (property "Value" "TPS54202"', 1)
        self.sch.write_text(sch)
        u1 = DesignContext.load(self.project_dir).component_detail("U1")
        self.assertEqual((u1["mpn"], u1["manufacturer"]), ("TPS54202DDCR", "Texas Instruments"))
        self.assertTrue(u1["datasheet"].endswith("tps54202.pdf"))


class TestTools(ProjectTestCase):
    def test_validation_and_errors(self):
        ws = Workspace(self.project_dir)
        self.assertIsNone(validate({"type": "object", "properties": {"refs": {"type": "array", "items": {"type": "string"}}},
                                    "required": ["refs"]}, {"refs": ["U1"]}))
        with self.assertRaises(ToolError):
            call(ws, "get_component", {"refs": "U1"})
        with self.assertRaises(ToolError):
            call(ws, "get_component", {"refs": ["U99"]})
        with self.assertRaises(ToolError):
            call(Workspace(), "get_design_overview", {})
        self.assertEqual(call(ws, "list_components", {"filter": "0805"})["count"], 8)

    def test_cache_reloads_after_save(self):
        ws = Workspace(self.project_dir)
        first = ws.context()
        self.assertIs(ws.context(), first)
        os.utime(self.pcb, ns=(self.pcb.stat().st_atime_ns, self.pcb.stat().st_mtime_ns + 10**9))
        self.assertIsNot(ws.context(), first)


class TestMCPServer(ProjectTestCase):
    def converse(self, *messages, project=True):
        server = MCPServer(self.project_dir if project else None, search_root=self.project_dir.parent)
        out = io.StringIO()
        server.serve(io.StringIO("\n".join(json.dumps(m) for m in messages) + "\n"), out)
        return [json.loads(line) for line in out.getvalue().splitlines()]

    def test_session(self):
        replies = self.converse(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_net", "arguments": {"net": "BOOT"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "get_net", "arguments": {"net": "NOPE"}}},
            {"jsonrpc": "2.0", "id": 5, "method": "nope"},
        )
        self.assertEqual([r["id"] for r in replies], [1, 2, 3, 4, 5])  # notification got no reply
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-06-18")
        names = {t["name"] for t in replies[1]["result"]["tools"]}
        self.assertLessEqual({"get_design_overview", "get_component", "run_design_review", "find_projects"}, names)
        net = json.loads(replies[2]["result"]["content"][0]["text"])
        self.assertEqual(sorted(n["ref"] for n in net["nodes"]), ["C_BOOT", "U1"])
        self.assertTrue(replies[3]["result"]["isError"])
        self.assertEqual(replies[4]["error"]["code"], -32601)

    def test_project_argument_and_discovery(self):
        replies = self.converse(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "find_projects", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "get_design_overview", "arguments": {"project": str(self.pcb)}}},
            project=False)
        self.assertIn(str(self.project_dir), json.loads(replies[0]["result"]["content"][0]["text"])["projects"])
        self.assertEqual(json.loads(replies[1]["result"]["content"][0]["text"])["component_count"], 11)


# ---------------------------------------------------------------- fake Claude API client
def block(type_, **kw):
    return NS(type=type_, **kw)


class FakeStream:
    def __init__(self, message, events):
        self.message, self.events = message, events

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self.events)

    def get_final_message(self):
        return self.message


class FakeClient:
    """Replays scripted turns and records each request's parameters."""

    def __init__(self, turns):
        self.turns, self.requests = list(turns), []
        self.beta = NS(messages=NS(stream=self.stream))

    def stream(self, **params):
        self.requests.append(json.loads(json.dumps(params, default=lambda o: vars(o))))
        content, stop = self.turns.pop(0)
        events = [NS(type="content_block_start", content_block=b) for b in content]
        events += [NS(type="text", text=b.text) for b in content if b.type == "text"]
        usage = NS(input_tokens=100, output_tokens=20, cache_read_input_tokens=0)
        return FakeStream(NS(content=content, stop_reason=stop, usage=usage), events)


class TestAssistantLoop(ProjectTestCase):
    def make(self, turns, **cfg):
        client = FakeClient(turns)
        return ai.Assistant(ai.Project(self.project_dir), {"model": "claude-opus-5-5", **cfg}, client=client), client

    def test_tool_round_trip_and_transcript(self):
        bot, client = self.make([
            ([block("server_tool_use", id="s1", name="web_search", input={"query": "TPS54202 stock"}),
              block("tool_use", id="t1", name="get_component", input={"refs": ["U1"]})], "tool_use"),
            ([block("text", text="U1 EN is tied to VIN.")], "end_turn"),
        ])
        statuses, chunks = [], []
        answer = bot.ask("Is U1 wired right?", on_text=chunks.append, on_status=statuses.append)
        self.assertEqual(answer, "U1 EN is tied to VIN.")
        self.assertIn("Searching the web…", statuses)
        first, second = client.requests
        self.assertEqual(first["model"], "claude-opus-5-5")
        self.assertEqual(first["output_config"], {"effort": "high"})
        self.assertEqual(first["fallbacks"], "default")
        tool_names = [t["name"] for t in first["tools"]]
        self.assertIn("web_search", tool_names)
        self.assertNotIn("find_projects", tool_names)
        self.assertTrue(all("project" not in t.get("input_schema", {}).get("properties", {}) for t in first["tools"]))
        self.assertIn("cache_control", first["system"][-1])
        result = second["messages"][-1]["content"][0]
        self.assertEqual(result["tool_use_id"], "t1")
        self.assertIn('"SW_NODE"', result["content"])
        path = bot.save_transcript()
        self.assertTrue(path.read_text().startswith("# Irona Assistant"))

    def test_bad_tool_input_is_returned_as_error(self):
        bot, client = self.make([
            ([block("tool_use", id="t1", name="get_component", input={"refs": "U1"})], "tool_use"),
            ([block("text", text="ok")], "end_turn"),
        ], web_search=False)
        bot.ask("x")
        result = client.requests[1]["messages"][-1]["content"][0]
        self.assertTrue(result["is_error"])
        self.assertNotIn("web_search", [t["name"] for t in client.requests[0]["tools"]])

    def test_pause_turn_resumes_and_refusal_stops(self):
        bot, client = self.make([
            ([block("server_tool_use", id="s1", name="web_search", input={})], "pause_turn"),
            ([block("text", text="partial")], "refusal"),
        ])
        answer = bot.ask("x")
        self.assertEqual(len(client.requests), 2)
        self.assertIn("declined", answer)

    def test_config_file_is_private(self):
        with mock.patch.object(ai, "CONFIG_PATH", self.project_dir / "cfg" / "assistant.json"):
            path = ai.save_config({"api_key": "test-key", **ai.DEFAULTS})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(ai.load_config()["api_key"], "test-key")
