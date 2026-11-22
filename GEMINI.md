# Irona for KiCad — project notes

Irona is a set of five KiCad action plugins plus a CLI for analysing and documenting boards that a
person designed. It does **not** generate schematics or layouts. The only LLM component is the Assistant
(`irona/assistant.py`, Claude API, optional `anthropic` dependency) and the MCP server (`irona/mcp_server.py`),
which answer questions about an existing design; both read it through `irona/assistant_tools.py`.

- Core library: `irona/` (standard library only, except `anthropic` for the Assistant). Plugins: `plugins/irona_{simulator,rule_check,design_review,docs,assistant}/`.
- Each plugin is a thin `__init__.py` (finds `irona/`, registers via `irona.kicad_ui.register_plugin`) and a `dialog.py`
  built on `irona.kicad_ui.IronaDialog` (Dracula palette from `irona/theme.py`).
- Output goes to `<project>/irona-out/`; simulator inputs persist in `<project>/irona-sim.json`.
- Never fabricate results: when an input or tool (e.g. kicad-cli) is missing, report the item as skipped.
- `irona/happy/` is vendored kicad-happy; avoid editing it, wrap it in `irona/circuit_review.py`.
- Tests: `python3 -m unittest discover -s tests -t .` (they copy `projects/*` into a temp dir).
- Dialogs can be exercised in KiCad's own Python: `flatpak run --command=python3 org.kicad.KiCad …`
  (stub `pcbnew.ActionPlugin.register`, which needs a running KiCad).

See README.md for usage.
