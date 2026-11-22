"""Assistant dialog: chat with Claude about the open design."""

import threading

from irona import assistant as ai
from irona import theme
from irona.kicad_ui import IronaDialog, colour, open_path

QUICK_PROMPTS = [
    ("Availability",
     "Check availability, lifecycle status (active / NRND / EOL) and typical price for every part in the BOM. "
     "For parts with no MPN, suggest orderable parts that match the value and footprint. Flag anything "
     "end-of-life, not recommended for new designs or out of stock, with alternates."),
    ("Datasheets",
     "Find the manufacturer datasheet for each active part (ICs, regulators, transistors, diodes, inductors, "
     "connectors). Give a table of reference, part, datasheet link, and note any Datasheet fields that are "
     "missing or point at the wrong part."),
    ("Review implementation",
     "Check whether each IC and the parts around it are implemented as its datasheet recommends: pin "
     "connections, voltage and current ratings with derating, required external components, and the values "
     "that set behaviour (feedback dividers, timing, current limits, soft-start). Show the calculations and "
     "rank the issues by severity."),
]


class Dialog(IronaDialog):
    title = "Assistant"
    size = (900, 720)

    def build_body(self, panel, sizer):
        wx = self.wx
        self.config = ai.load_config()
        self.assistant = None
        self.busy = False

        top = wx.BoxSizer(wx.HORIZONTAL)
        self.model_label = wx.StaticText(panel, label="")
        self.model_label.SetForegroundColour(colour(theme.COMMENT))
        self.model_label._irona_keep_fg = True
        top.Add(self.model_label, 1, wx.ALIGN_CENTER_VERTICAL)
        self.effort = wx.Choice(panel, choices=list(ai.EFFORTS))
        self.effort.SetStringSelection(self.config.get("effort", "high"))
        self.effort.Bind(wx.EVT_CHOICE, lambda _e: self._set_effort())
        self.labelled(top, "Effort", self.effort, border=8)
        top.Add(self.button("API key…", self.on_api_key), 0, wx.RIGHT, 8)
        self.save_btn = self.button("Save chat", self.on_save)
        top.Add(self.save_btn, 0, wx.RIGHT, 8)
        top.Add(self.button("New chat", self.on_new_chat))
        sizer.Add(top, 0, wx.EXPAND | wx.BOTTOM, 10)

        self.log = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.TE_WORDWRAP
                               | wx.BORDER_NONE)
        self.log.SetFont(wx.Font(wx.FontInfo(10)))
        sizer.Add(self.log, 1, wx.EXPAND | wx.BOTTOM, 10)

        quick = wx.BoxSizer(wx.HORIZONTAL)
        self.quick_btns = []
        for label, prompt in QUICK_PROMPTS:
            b = self.button(label, lambda p=prompt: self.send(p))
            quick.Add(b, 0, wx.RIGHT, 8)
            self.quick_btns.append(b)
        sizer.Add(quick, 0, wx.BOTTOM, 8)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.entry = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_PROCESS_ENTER | wx.BORDER_NONE, size=(-1, 64))
        self.entry.SetHint("Ask about this design…  (Enter to send, Shift+Enter for a new line)")
        self.entry.Bind(wx.EVT_KEY_DOWN, self._on_key)
        row.Add(self.entry, 1, wx.EXPAND | wx.RIGHT, 8)
        self.send_btn = self.button("Send", lambda: self.send(self.entry.GetValue()), primary=True)
        row.Add(self.send_btn, 0, wx.ALIGN_BOTTOM)
        sizer.Add(row, 0, wx.EXPAND)

        self._refresh_header()
        self._greet()

    # ---- state
    def _refresh_header(self):
        web = "web search on" if self.config.get("web_search", True) else "web search off"
        self.model_label.SetLabel(f"Claude · {self.config['model']} · {web}")

    def _set_effort(self):
        self.config["effort"] = self.effort.GetStringSelection()
        ai.save_config(self.config)
        if self.assistant:
            self.assistant.config["effort"] = self.config["effort"]

    def _greet(self):
        if not self.project or not self.project.pcb:
            self._note("Save the board, then reopen the Assistant.")
        elif not ai.sdk_available():
            self._note(ai.INSTALL_HINT)
        elif not ai.has_credentials(self.config):
            self._note("Add your Anthropic API key with “API key…” to start. It is stored in "
                       f"{ai.CONFIG_PATH} (readable only by you).")
        else:
            self._note("Ask anything about this board, or use a quick action below. Claude reads the saved "
                       "schematic and board, and searches the web for stock and datasheets.")
        self._enable(True)

    def _enable(self, on: bool):
        ready = bool(self.project and self.project.pcb and ai.sdk_available())
        for w in [self.send_btn, self.entry] + self.quick_btns:
            w.Enable(on and ready)
        self.save_btn.Enable(bool(self.assistant and self.assistant.transcript) and on)

    # ---- transcript rendering
    def _write(self, text: str, hex_colour: str = theme.FOREGROUND, bold: bool = False):
        wx = self.wx
        font = self.log.GetFont()
        attr = wx.TextAttr(colour(hex_colour), colour(theme.SURFACE), font.Bold() if bold else font)
        self.log.SetDefaultStyle(attr)
        self.log.AppendText(text)
        self.log.ShowPosition(self.log.GetLastPosition())

    def _note(self, text: str):
        self._write(text + "\n\n", theme.COMMENT)

    def _heading(self, who: str):
        if self.log.GetLastPosition():
            self._write("\n")
        self._write(("You" if who == "you" else "Claude") + "\n", theme.PURPLE if who == "you" else theme.CYAN, bold=True)

    # ---- actions
    def _on_key(self, evt):
        if evt.GetKeyCode() in (self.wx.WXK_RETURN, self.wx.WXK_NUMPAD_ENTER) and not evt.ShiftDown():
            self.send(self.entry.GetValue())
        else:
            evt.Skip()

    def send(self, text: str):
        text = (text or "").strip()
        if not text or self.busy or not self.require_project():
            return
        if not ai.has_credentials(self.config):
            self.on_api_key()
            if not ai.has_credentials(self.config):
                return
        if self.assistant is None:
            self.assistant = ai.Assistant(self.project, self.config)
        self.entry.SetValue("")
        self._heading("you")
        self._write(text + "\n")
        self._heading("claude")
        self.busy = True
        self._enable(False)
        self.set_status("Thinking…")
        threading.Thread(target=self._worker, args=(text,), daemon=True).start()

    def _worker(self, text: str):
        wx = self.wx
        call = lambda fn, *a: wx.CallAfter(lambda: fn(*a) if self.dialog else None)  # noqa: E731
        try:
            self.assistant.ask(text,
                               on_text=lambda t: call(self._write, t),
                               on_status=lambda s: call(self.set_status, s))
            call(self._done, None)
        except Exception as e:  # shown in the chat
            call(self._done, str(e) or e.__class__.__name__)

    def _done(self, error):
        self.busy = False
        if error:
            self._write("\n" + error + "\n", theme.RED)
            self.set_status("Failed", "error")
        else:
            self._write("\n")
            u = self.assistant.usage
            self.set_status(f"{u['input_tokens'] + u['cache_read_input_tokens']:,} tokens in · "
                            f"{u['output_tokens']:,} out this chat")
        self._enable(True)
        self.entry.SetFocus()

    def on_api_key(self):
        wx = self.wx
        dlg = wx.PasswordEntryDialog(self.dialog, "Anthropic API key (from console.anthropic.com):", "Claude API key")
        if dlg.ShowModal() == wx.ID_OK and dlg.GetValue().strip():
            self.config["api_key"] = dlg.GetValue().strip()
            path = ai.save_config(self.config)
            self.assistant = None  # rebuild the client with the new key
            self._note(f"API key saved to {path}.")
            self._enable(True)
        dlg.Destroy()

    def on_new_chat(self):
        if self.busy:
            return
        self.assistant = None
        self.log.SetValue("")
        self.set_status("")
        self._greet()

    def on_save(self):
        if self.assistant:
            path = self.assistant.save_transcript()
            if path:
                self.set_status(f"Saved {path.name}", "pass")
                open_path(path)
