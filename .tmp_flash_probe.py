import collections, os, pathlib, sys, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
tmp = pathlib.Path(tempfile.mkdtemp(prefix="flash-probe-"))
os.environ["CLAUDE_CONFIG_DIR"] = str(tmp / "claude")
os.environ["CLAUDE_STATUS_DESKTOP_DIR"] = str(tmp / "desktop")
from PySide6 import QtCore, QtWidgets
import md3
from claude_status import app as app_module, claude_desktop, main_window, state as state_module, storage
claude_desktop.request_quit = claude_desktop.force_quit = claude_desktop.launch = None

shown = collections.Counter()
class Probe(QtCore.QObject):
    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Type.Show and isinstance(obj, QtWidgets.QWidget) and obj.isWindow():
            if not isinstance(obj, main_window.MainWindow):
                text = obj.text() if hasattr(obj, "text") and callable(obj.text) else ""
                shown[f"{type(obj).__module__}.{type(obj).__name__} {str(text)[:24]!r}"] += 1
        return False

app = QtWidgets.QApplication([])
probe = Probe(); app.installEventFilter(probe)
state = state_module.AppState(storage.Store(tmp / "data"), force_demo=True, offline=True)
md3.install(app, seed=state.settings.seed, font_family=app_module.font_family(), extended=app_module.EXTENDED_COLORS, locale="zh")
window = main_window.MainWindow(state)
window.show(); state.refresh(); app_module._wait(1500)
for key in main_window.PAGE_KEYS:
    window.show_page(key); app_module._wait(300)
print("top-level windows shown besides the main window:", sum(shown.values()))
for name, count in shown.most_common(20):
    print(f"{count:4d}  {name}")
state.shutdown()
