"""
Shared pieces for the Irona KiCad action plugins: plugin registration, the active-board lookup,
and a minimal Dracula-themed wx dialog with a results list.

Only `register_plugin` is imported at KiCad start-up; wx is imported when a dialog is opened, so
the plugins can be imported (and tested) without wx or pcbnew.
"""

import logging
import subprocess
import threading
import traceback
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence

from irona import theme
from irona.project import Project

logger = logging.getLogger(__name__)

try:
    import pcbnew  # type: ignore
except ImportError:  # running outside KiCad (tests, CLI)
    pcbnew = None


# --------------------------------------------------------------------------- registration
def register_plugin(name: str, description: str, icon: Path, open_dialog: Callable[[Any, Optional[str]], None]):
    """Creates and registers a pcbnew ActionPlugin. Returns the plugin instance (or None outside KiCad)."""
    if pcbnew is None:
        return None

    class _Plugin(pcbnew.ActionPlugin):
        def defaults(self):
            self.name = name
            self.category = "Irona"
            self.description = description
            self.show_toolbar_button = True
            self.icon_file_name = str(icon)
            self.dark_icon_file_name = str(icon)

        def Run(self):
            board = pcbnew.GetBoard()
            path = board.GetFileName() if board else None
            try:
                open_dialog(board, path or None)
            except Exception:
                import wx
                wx.MessageBox(traceback.format_exc(), f"{name} failed", wx.OK | wx.ICON_ERROR)

    _Plugin.__name__ = "Irona" + "".join(w.capitalize() for w in name.split()) + "Plugin"
    plugin = _Plugin()
    plugin.register()
    return plugin


def project_for(board_path: Optional[str]) -> Optional[Project]:
    if not board_path or not Path(board_path).exists():
        return None
    return Project.from_board(Path(board_path))


def open_path(path: Path) -> None:
    """Opens a file or folder with the desktop's default handler (works from KiCad's flatpak via the portal)."""
    try:
        subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        logger.warning("Could not open %s", path)


# --------------------------------------------------------------------------- wx widgets
def _wx():
    import wx  # noqa: WPS433 (deferred so plugins import without wx)
    return wx


def colour(hex_value: str):
    return _wx().Colour(*theme.hex_to_rgb(hex_value))


def style_tree(window) -> None:
    """Applies Dracula colours to a window and all of its children."""
    wx = _wx()
    bg, fg = colour(theme.BACKGROUND), colour(theme.FOREGROUND)
    surface = colour(theme.SURFACE)
    for w in [window] + list(_descendants(window)):
        if isinstance(w, (wx.TextCtrl, wx.ListCtrl, wx.SpinCtrlDouble, wx.Choice)):
            w.SetBackgroundColour(surface)
            w.SetForegroundColour(fg)
        elif isinstance(w, wx.Button):
            w.SetBackgroundColour(colour(theme.CURRENT_LINE))
            w.SetForegroundColour(fg)
        else:
            w.SetBackgroundColour(bg)
            if not getattr(w, "_irona_keep_fg", False):
                w.SetForegroundColour(fg)


def _descendants(window):
    for child in window.GetChildren():
        yield child
        yield from _descendants(child)


class IronaDialog:
    """
    Base dialog: a title, a muted subtitle, a body supplied by the subclass, a status line and
    Close. Subclasses implement `build_body(panel, sizer)`.
    """

    title = "Irona"
    size = (820, 560)

    def __init__(self, parent, board, board_path: Optional[str]):
        wx = _wx()
        self.wx = wx
        self.board = board
        self.board_path = board_path
        self.project = project_for(board_path)

        self.dialog = wx.Dialog(parent, title=self.title, size=self.size,
                                style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.dialog.SetMinSize((620, 420))
        panel = wx.Panel(self.dialog)
        self.panel = panel
        outer = wx.BoxSizer(wx.VERTICAL)

        heading = wx.StaticText(panel, label=self.title)
        heading.SetFont(heading.GetFont().Bold().Scaled(1.35))
        outer.Add(heading, 0, wx.LEFT | wx.RIGHT | wx.TOP, 16)

        self.subtitle = wx.StaticText(panel, label=self.describe_board())
        self.subtitle.SetForegroundColour(colour(theme.COMMENT))
        self.subtitle._irona_keep_fg = True
        outer.Add(self.subtitle, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)

        body = wx.BoxSizer(wx.VERTICAL)
        self.build_body(panel, body)
        outer.Add(body, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 16)

        footer = wx.BoxSizer(wx.HORIZONTAL)
        self.status = wx.StaticText(panel, label="")
        self.status.SetForegroundColour(colour(theme.COMMENT))
        self.status._irona_keep_fg = True
        footer.Add(self.status, 1, wx.ALIGN_CENTER_VERTICAL)
        close = wx.Button(panel, wx.ID_CLOSE, "Close")
        close.Bind(wx.EVT_BUTTON, lambda _e: self.dialog.Destroy())
        footer.Add(close, 0)
        outer.Add(footer, 0, wx.EXPAND | wx.ALL, 16)

        panel.SetSizer(outer)
        style_tree(self.dialog)
        self.dialog.CentreOnParent()

    # ---- helpers for subclasses
    def describe_board(self) -> str:
        if not self.project or not self.project.pcb:
            return "Save the board first: Irona analyses the files on disk."
        note = ""
        try:
            if self.board is not None and self.board.IsModified():
                note = "  ·  unsaved changes are not included"
        except Exception:
            pass
        return f"{self.project.pcb.name}  ·  {self.project.dir}{note}"

    def button(self, label: str, handler: Callable[[], None], primary: bool = False):
        wx = self.wx
        b = wx.Button(self.panel, label=label)
        b.Bind(wx.EVT_BUTTON, lambda _e: handler())
        if primary:
            b.SetDefault()
            self._primary = b
        return b

    def labelled(self, sizer, label: str, ctrl, border: int = 12) -> None:
        wx = self.wx
        t = wx.StaticText(self.panel, label=label)
        t.SetForegroundColour(colour(theme.COMMENT))
        t._irona_keep_fg = True
        sizer.Add(t, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        sizer.Add(ctrl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border)

    def set_status(self, text: str, tone: str = "") -> None:
        self.status.SetLabel(text)
        self.status.SetForegroundColour(colour(theme.severity_colour(tone) if tone else theme.COMMENT))
        self.status.GetParent().Layout()

    def run_async(self, work: Callable[[], Any], done: Callable[[Any], None], busy_text: str = "Running…") -> None:
        """Runs `work` off the UI thread, then calls `done(result)` on it. Errors go to the status line."""
        wx = self.wx
        self.set_status(busy_text)
        self.panel.Disable()
        wx.BeginBusyCursor()

        def finish(result=None, error=None):
            if wx.IsBusy():
                wx.EndBusyCursor()
            if not self.dialog:  # closed while running
                return
            self.panel.Enable()
            if error:
                self.set_status(f"Failed: {error}", "error")
                logger.error(error)
            else:
                done(result)

        def target():
            try:
                res = work()
            except Exception as e:  # surfaced in the dialog
                logger.debug(traceback.format_exc())
                wx.CallAfter(finish, None, str(e) or e.__class__.__name__)
            else:
                wx.CallAfter(finish, res, None)

        threading.Thread(target=target, daemon=True).start()

    def require_project(self) -> bool:
        if self.project and self.project.pcb:
            return True
        self.set_status("No saved board found.", "error")
        return False

    def build_body(self, panel, sizer) -> None:
        raise NotImplementedError

    def show(self) -> None:
        self.dialog.Show()


class ResultList:
    """A report-style list whose rows are tinted by severity (first column)."""

    def __init__(self, dlg: IronaDialog, columns: Sequence[tuple]):
        wx = dlg.wx
        self.ctrl = wx.ListCtrl(dlg.panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_NONE)
        for i, (label, width) in enumerate(columns):
            self.ctrl.InsertColumn(i, label, width=width)
        self.rows: List[tuple] = []

    def clear(self) -> None:
        self.ctrl.DeleteAllItems()
        self.rows = []

    def add(self, severity: str, *cells: Any) -> None:
        idx = self.ctrl.InsertItem(self.ctrl.GetItemCount(), str(severity))
        for col, value in enumerate(cells, start=1):
            self.ctrl.SetItem(idx, col, "" if value is None else str(value))
        self.ctrl.SetItemTextColour(idx, colour(theme.severity_colour(severity)))
        self.rows.append((severity,) + cells)

    def fit_last_column(self) -> None:
        n = self.ctrl.GetColumnCount()
        if n:
            self.ctrl.SetColumnWidth(n - 1, self.ctrl.GetSize().width - sum(self.ctrl.GetColumnWidth(i) for i in range(n - 1)) - 4)


def show_dialog(dialog_cls, board, board_path: Optional[str]) -> None:
    """Opens `dialog_cls` modelessly over the PCB editor."""
    wx = _wx()
    parent = None
    try:
        parent = next((w for w in wx.GetTopLevelWindows() if "pcb" in w.GetTitle().lower()), None)
    except Exception:
        pass
    dialog_cls(parent, board, board_path).show()

