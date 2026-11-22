"""
Design assistant backed by the Claude API: answers questions about the open KiCad project, checks
part availability and datasheets on the web, and reviews whether parts are connected the way their
datasheets require.

Claude reads the design through the tools in `irona.assistant_tools` and the web through the
server-side web search / web fetch tools. Requires the `anthropic` package and an API key (from
the Assistant dialog, $ANTHROPIC_API_KEY, or an `ant auth login` profile).
"""

import json
import logging
import os
import stat
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from irona import assistant_tools as tools_mod
from irona.assistant_tools import ToolError, Workspace
from irona.project import Project

logger = logging.getLogger(__name__)

CONFIG_PATH = Path.home() / ".config" / "irona" / "assistant.json"
DEFAULTS = {"model": "claude-opus-5-5", "effort": "high", "web_search": True}
EFFORTS = ("low", "medium", "high", "xhigh", "max")
MAX_TURNS = 24          # model round-trips per question (tool calls + pause_turn resumes)
MAX_TOKENS = 64000

SYSTEM_PROMPT = """You are an electronics design reviewer working inside KiCad, helping the designer of the project described below.

You can read the design with the project tools (parts, fields, pin-to-net connectivity, and Irona's rule check, design review and simulation) and the web with web_search and web_fetch.

How to work:
- Ground every statement about the design in tool results; look up pins with get_component before judging a connection.
- For availability, stock, pricing, lifecycle (active / NRND / EOL) and alternates, search distributor and manufacturer sites (Digi-Key, Mouser, LCSC, Farnell, Octopart, the manufacturer's product page). Give the date-sensitive facts with their source links and say they can change.
- For "is this implemented correctly", find the part's datasheet (use the Datasheet field when present), and compare the actual connections and values with it: pin functions, absolute maximum ratings and derating, required external parts (decoupling, bootstrap, compensation, pull-ups), feedback divider and output voltage arithmetic, enable and power-good handling, and the recommended layout notes. Show the calculations.
- When a part has no MPN, say which orderable parts would match its value and footprint rather than assuming one.
- Be direct: lead with problems ranked by severity, then what is fine. Mark anything you could not verify.
- Irona analyses the saved files, so remind the designer to save if results look stale."""


# --------------------------------------------------------------------------- settings
def load_config() -> Dict[str, Any]:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg: Dict[str, Any]) -> Path:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    os.chmod(CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)  # holds the API key
    return CONFIG_PATH


def sdk_available() -> bool:
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def has_credentials(cfg: Optional[Dict[str, Any]] = None) -> bool:
    cfg = cfg or load_config()
    return bool(cfg.get("api_key") or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or (Path.home() / ".config" / "anthropic").is_dir())


INSTALL_HINT = (
    "The Assistant needs the `anthropic` Python package in KiCad's Python. Install it with:\n"
    "    python3 install_kicad_plugins.py --assistant-deps\n"
    "or for the CLI:  pip install anthropic"
)


def _sdk_errors():
    """The SDK exception classes the chat turns into readable messages (placeholders without the SDK)."""
    try:
        import anthropic
    except ImportError:
        class _Never(Exception):
            pass
        return (_Never,) * 4
    return (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.RateLimitError,
            anthropic.APIConnectionError)


# --------------------------------------------------------------------------- assistant
class Assistant:
    """One conversation about one project. Not thread-safe: run `ask` from a single worker thread."""

    def __init__(self, project: Project, config: Optional[Dict[str, Any]] = None, client: Any = None):
        self.project = project
        self.config = {**DEFAULTS, **(config or load_config())}
        self.ws = Workspace(project.dir)
        self.messages: List[Dict[str, Any]] = []
        self.transcript: List[tuple] = []
        self._client = client
        self._system: Optional[List[Dict[str, Any]]] = None
        self.usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0}

    # ---- setup
    @property
    def client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise RuntimeError(INSTALL_HINT) from None
            key = self.config.get("api_key")
            self._client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
        return self._client

    def tool_definitions(self) -> List[Dict[str, Any]]:
        defs = [{"name": t["name"], "description": t["description"],
                 "input_schema": tools_mod.without_project(t["input_schema"]),
                 "eager_input_streaming": True}
                for t in tools_mod.TOOLS if t["name"] != "find_projects"]
        if self.config.get("web_search", True):
            defs += [{"type": "web_search_20260209", "name": "web_search"},
                     {"type": "web_fetch_20260209", "name": "web_fetch"}]
        return defs

    def system_blocks(self) -> List[Dict[str, Any]]:
        overview = self.ws.context().overview()
        # Stable for the whole conversation, so it is cached after the first request.
        return [{"type": "text", "text": SYSTEM_PROMPT},
                {"type": "text", "text": "Design overview (from the saved files when the chat started):\n"
                                         + json.dumps(overview, indent=1),
                 "cache_control": {"type": "ephemeral"}}]

    def reset(self) -> None:
        self.messages, self.transcript = [], []
        self._system = None

    # ---- the loop
    def ask(self, question: str,
            on_text: Callable[[str], None] = lambda _t: None,
            on_status: Callable[[str], None] = lambda _s: None) -> str:
        """Sends a question, runs tools until Claude answers, streams text through `on_text`."""
        auth_err, perm_err, rate_err, conn_err = _sdk_errors()
        if not self._system:
            self._system = self.system_blocks()
        self.messages.append({"role": "user", "content": question})
        self.transcript.append(("you", question))
        answer: List[str] = []
        json_retries = 0

        for _turn in range(MAX_TURNS):
            on_status("Thinking…")
            try:
                with self.client.beta.messages.stream(
                    model=self.config["model"],
                    max_tokens=MAX_TOKENS,
                    system=self._system,
                    tools=self.tool_definitions(),
                    messages=self.messages,
                    output_config={"effort": self.config.get("effort", "high")},
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                ) as stream:
                    for event in stream:
                        if event.type == "text":
                            answer.append(event.text)
                            on_text(event.text)
                        elif event.type == "content_block_start":
                            block = event.content_block
                            if block.type == "server_tool_use":
                                on_status("Searching the web…" if block.name == "web_search" else "Reading a web page…")
                            elif block.type == "tool_use":
                                on_status(f"Reading the design ({block.name})…")
                    response = stream.get_final_message()
                json_retries = 0
            except ValueError:
                # Tool input JSON the SDK could not parse; re-issue the turn (bounded).
                json_retries += 1
                if json_retries > 2:
                    raise
                continue
            except auth_err:
                raise RuntimeError("The API key was rejected. Set a valid key with “API key…”.") from None
            except perm_err as e:
                raise RuntimeError(f"The API key lacks access: {getattr(e, 'message', e)}") from None
            except rate_err:
                raise RuntimeError("Rate limited by the Claude API; wait a moment and ask again.") from None
            except conn_err:
                raise RuntimeError("Could not reach the Claude API. Check the network connection.") from None

            self._count(response.usage)
            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "pause_turn":  # long server-side web research; resume it
                continue
            if response.stop_reason == "refusal":
                note = "\n\n[Claude declined to continue this request.]"
                answer.append(note)
                on_text(note)
                break

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                break
            if response.stop_reason == "max_tokens":
                note = "\n\n[The answer hit the length limit; ask a narrower question.]"
                answer.append(note)
                on_text(note)
                break

            results = []
            for block in tool_uses:
                on_status(f"Reading the design ({block.name})…")
                results.append(self._run_tool(block))
            self.messages.append({"role": "user", "content": results})
            if answer and not answer[-1].endswith("\n"):
                answer.append("\n\n")
                on_text("\n\n")
        else:
            note = "\n\n[Stopped after too many steps; ask a narrower question.]"
            answer.append(note)
            on_text(note)

        text = "".join(answer).strip()
        self.transcript.append(("claude", text))
        on_status("")
        return text

    def _run_tool(self, block) -> Dict[str, Any]:
        try:
            data = tools_mod.call(self.ws, block.name, block.input, include_project_arg=False)
            return {"type": "tool_result", "tool_use_id": block.id, "content": tools_mod.to_json(data)}
        except ToolError as e:
            return {"type": "tool_result", "tool_use_id": block.id, "content": str(e), "is_error": True}
        except Exception as e:  # analysis failure: let Claude carry on without it
            logger.exception("tool %s failed", block.name)
            return {"type": "tool_result", "tool_use_id": block.id, "content": f"{block.name} failed: {e}",
                    "is_error": True}

    def _count(self, usage) -> None:
        for k in self.usage:
            self.usage[k] += getattr(usage, k, 0) or 0

    # ---- transcript
    def save_transcript(self) -> Optional[Path]:
        if not self.transcript:
            return None
        out = self.project.output_dir / "assistant"
        out.mkdir(parents=True, exist_ok=True)
        path = out / time.strftime("chat-%Y%m%d-%H%M%S.md")
        lines = [f"# Irona Assistant: {self.project.name}", "",
                 f"Model {self.config['model']}, effort {self.config.get('effort')}", ""]
        for who, text in self.transcript:
            lines += [f"## {'You' if who == 'you' else 'Claude'}", "", text, ""]
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
