"""BoatGen - boat generator for Brick Rigs.

Run:  BoatGen.exe             (built by GitHub Actions / build_exe.bat)
      python app.py           (own app window: Qt WebEngine, PySide6)
      python app.py --browser (no PySide6: the same interface in an Edge/Chrome app window)
"""
import base64
import json
import os
import random
import shutil
import subprocess
import sys
import threading
import traceback

APP_NAME = "BoatGen"
VERSION = "1.0"


# ----------------------------------------------------------------------------- paths
def resource_dir():
    """Folder with ui/ and engine/data (inside the bundle when frozen by PyInstaller)."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def app_dir():
    """Folder next to BoatGen.exe (or app.py): output and settings live here."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    here = os.path.dirname(os.path.abspath(__file__))
    # running from BoatGen/source/app.py -> keep boats and settings in BoatGen/
    return os.path.dirname(here) if os.path.basename(here).lower() == "source" else here


sys.path.insert(0, resource_dir())
from engine.gen import generate, write_vehicle  # noqa: E402
from engine.mesh import scene  # noqa: E402

OUTPUT = os.path.join(app_dir(), "Boats")
SETTINGS = os.path.join(app_dir(), "settings.json")


def game_vehicles_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
    return os.path.join(base, "BrickRigs", "SavedRemastered", "Vehicles")


def load_settings():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data):
    try:
        with open(SETTINGS, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


CONTROLS = {
    "ru": {"throttle": "W / S — вперёд / назад", "steer": "A / D — поворот моторов",
           "lights": "Фары и ходовые огни — ось «Фары», маячки — «Маячок»",
           "door_aft": "Действие 3 — кормовая дверь рубки", "door_side": "Действие 4 — боковые двери",
           "gun": "Пушка: сядьте в левое переднее кресло рубки, мышь — наведение, ЛКМ — огонь",
           "stab": "Стабилизаторы крена и дифферента работают сами"},
    "en": {"throttle": "W / S — forward / reverse", "steer": "A / D — turn the outboards",
           "lights": "Head and navigation lights — Headlight axis, beacons — Beacon",
           "door_aft": "Action 3 — aft cabin door", "door_side": "Action 4 — side doors",
           "gun": "Gun: take the front-left cabin seat, mouse aims, LMB fires",
           "stab": "Roll and pitch stabilisers work automatically"},
}


def controls(kind, lang):
    t = CONTROLS.get(lang, CONTROLS["ru"])
    keys = ["throttle", "steer"]
    if kind in ("cutter", "military"):
        keys.append("door_aft")
    if kind == "military":
        keys += ["door_side", "gun"]
    if kind in ("cutter", "military"):
        keys.append("stab")
    keys.append("lights")
    return [t[k] for k in keys]


# ----------------------------------------------------------------------------- API
class Api:
    def __init__(self):
        self._settings = load_settings()
        self._last = None
        self._params = None
        self._saved = None
        self._lock = threading.Lock()
        self._window = None

    # -- settings
    def get_state(self):
        return {"lang": self._settings.get("lang", "ru"), "version": VERSION,
                "game_dir": game_vehicles_dir(), "game_found": os.path.isdir(game_vehicles_dir()),
                "output": OUTPUT, "last": self._settings.get("last")}

    def set_lang(self, lang):
        self._settings["lang"] = lang if lang in ("ru", "en") else "ru"
        save_settings(self._settings)
        return True

    # -- generation
    def generate(self, params, reroll=False):
        with self._lock:
            try:
                kind = params.get("kind", "military")
                size = params.get("size", "M")
                detail = params.get("detail", "med")
                color = params.get("color", "dark")
                lang = params.get("lang", self._settings.get("lang", "ru"))
                seed = random.randint(1, 999999)
                r = generate(kind, size, detail, color, seed)
                self._last, self._params, self._saved = r, dict(params), None
                self._settings["last"] = {"kind": kind, "size": size, "detail": detail, "color": color}
                save_settings(self._settings)
                i = r.info
                return {"ok": True, "name": r.name, "scene": scene(r),
                        "info": {"bricks": i["bricks"], "length": i["length_m"], "beam": i["beam_m"],
                                 "mass": round(i["mass"] / 1000.0, 1), "draft": round(i["draft"], 1),
                                 "sections": i["weld_groups"], "in_range": i["in_range"], "seed": seed,
                                 "pitch": round(i.get("pitch", 0.0), 1),
                                 "engines": getattr(r.builder, "n_out", 1),
                                 "stab": ("%.1f / %.1f" % r.builder.stab_k) if getattr(r.builder, "stab_thr", None) else ""},
                        "controls": controls(kind, lang)}
            except Exception as e:
                traceback.print_exc()
                return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}

    def save(self, png_data_url=None):
        with self._lock:
            if self._last is None:
                return {"ok": False, "error": "nothing generated"}
            try:
                os.makedirs(OUTPUT, exist_ok=True)
                name = self._last.name
                folder = os.path.join(OUTPUT, name)
                n = 2
                while os.path.exists(folder):
                    folder = os.path.join(OUTPUT, "%s (%d)" % (name, n))
                    n += 1
                png = None
                if png_data_url and "," in png_data_url:
                    png = base64.b64decode(png_data_url.split(",", 1)[1])
                write_vehicle(self._last, folder, png)
                lang = (self._params or {}).get("lang", "ru")
                with open(os.path.join(folder, "README.txt"), "w", encoding="utf-8") as f:
                    f.write("%s - BoatGen %s\n\n" % (name, VERSION))
                    f.write("\n".join(controls(self._last.info["kind"], lang)) + "\n")
                self._saved = folder
                return {"ok": True, "path": folder, "folder": os.path.basename(folder),
                        "game_dir": game_vehicles_dir(), "game_found": os.path.isdir(game_vehicles_dir())}
            except Exception as e:
                traceback.print_exc()
                return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}

    def copy_to_game(self):
        if not self._saved:
            return {"ok": False, "error": "not saved"}
        dst_root = game_vehicles_dir()
        if not os.path.isdir(dst_root):
            return {"ok": False, "error": "game folder not found", "game_dir": dst_root}
        try:
            dst = os.path.join(dst_root, os.path.basename(self._saved))
            n = 2
            while os.path.exists(dst):
                dst = os.path.join(dst_root, "%s (%d)" % (os.path.basename(self._saved), n))
                n += 1
            shutil.copytree(self._saved, dst)
            return {"ok": True, "path": dst}
        except Exception as e:
            return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}

    def open_folder(self, path=None):
        path = path or self._saved or OUTPUT
        os.makedirs(path, exist_ok=True) if path == OUTPUT else None
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            return True
        except Exception:
            return False

    def toggle_fullscreen(self):
        f = getattr(self, "_window", None)
        if f is None:
            return False
        f()
        return True

    def exit_fullscreen(self):
        f = getattr(self, "_exitfs", None)
        if f is None:
            return False
        f()
        return True

    def open_url(self, url):
        if not str(url).startswith("https://steamcommunity.com/"):
            return False
        import webbrowser
        webbrowser.open(url)
        return True

    def open_game_folder(self):
        return self.open_folder(game_vehicles_dir()) if os.path.isdir(game_vehicles_dir()) else False


# ----------------------------------------------------------------------------- browser fallback
def open_app_window(url):
    """Open the interface as a separate app window (Edge/Chrome --app: no tabs, no address bar)."""
    if not sys.platform.startswith("win"):
        return False
    pf = [os.environ.get(k, "") for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    cands = [os.path.join(b, *rel) for b in pf if b for rel in (
        ("Microsoft", "Edge", "Application", "msedge.exe"), ("Google", "Chrome", "Application", "chrome.exe"))]
    prof = os.path.join(app_dir(), "window_profile")
    for exe in cands:
        if os.path.isfile(exe):
            try:
                subprocess.Popen([exe, "--app=" + url, "--window-size=1180,800", "--user-data-dir=" + prof,
                                  "--no-first-run", "--no-default-browser-check"])
                return True
            except Exception:
                continue
    return False


def make_server(api, port=0):
    """Local HTTP server: serves ui/ and answers POST /api/<method> with JSON."""
    import http.server
    import socketserver
    ui = os.path.join(resource_dir(), "ui")

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=ui, **k)

        def log_message(self, *a):
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_POST(self):
            if not self.path.startswith("/api/"):
                self.send_error(404)
                return
            name = self.path[5:]
            n = int(self.headers.get("Content-Length") or 0)
            args = json.loads(self.rfile.read(n) or b"[]")
            fn = getattr(api, name, None)
            if fn is None or name.startswith("_"):
                self.send_error(404)
                return
            out = json.dumps(fn(*args)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", port), H)
    srv.daemon_threads = True
    url = "http://127.0.0.1:%d/index.html?browser=1" % srv.server_address[1]
    return srv, url


def run_browser(api, port=0, open_browser=True):
    import webbrowser
    srv, url = make_server(api, port)
    print("BoatGen:", url)
    if open_browser:
        if not open_app_window(url):
            webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def log_error(text):
    try:
        with open(os.path.join(app_dir(), "error.log"), "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass


def run_qt(api, test=False):
    """BoatGen as a real desktop application: a Qt window with its own Chromium (QtWebEngine),
    so it needs neither WebView2 nor a browser."""
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--ignore-gpu-blocklist --autoplay-policy=no-user-gesture-required")
    from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
    from PySide6.QtGui import QDesktopServices, QIcon
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication, QMainWindow

    srv, url = make_server(api)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    local = url.split("/index.html")[0]

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("BoatGen")
    icon_path = os.path.join(resource_dir(), "ui", "icon.png")

    class Page(QWebEnginePage):
        """Links that leave the app (Steam etc.) open in the system browser."""
        def acceptNavigationRequest(self, qurl, nav_type, is_main):
            if not qurl.toString().startswith(local):
                QDesktopServices.openUrl(qurl)
                return False
            return super().acceptNavigationRequest(qurl, nav_type, is_main)

        def createWindow(self, _type):
            page = Page(self)
            page.urlChanged.connect(lambda u: (QDesktopServices.openUrl(u), page.deleteLater()))
            return page

    class Bridge(QObject):
        toggle = Signal()
        leave = Signal()

    win = QMainWindow()
    win.setWindowTitle("BoatGen")
    if os.path.isfile(icon_path):
        win.setWindowIcon(QIcon(icon_path))
    win.resize(1180, 800)
    win.setMinimumSize(940, 660)
    win.setStyleSheet("background:#0a111c;")
    view = QWebEngineView()
    page = Page(view)
    view.setPage(page)
    st = page.settings()
    st.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
    st.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
    view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
    win.setCentralWidget(view)

    bridge = Bridge()

    def toggle():
        if win.isFullScreen():
            win.showNormal()
        else:
            win.showFullScreen()
    bridge.toggle.connect(toggle, Qt.ConnectionType.QueuedConnection)
    bridge.leave.connect(lambda: win.isFullScreen() and win.showNormal(), Qt.ConnectionType.QueuedConnection)
    api._window = bridge.toggle.emit
    api._exitfs = bridge.leave.emit

    if test:
        out = os.path.join(app_dir(), "guitest.txt")

        def probe(n=[0]):
            n[0] += 1

            def got(res):
                if res == "ok" or n[0] > 40:
                    with open(out, "w") as f:
                        f.write(str(res))
                    app.quit()
                else:
                    QTimer.singleShot(1000, probe)
            page.runJavaScript("window.__boatgen && document.querySelector('#startBtn') ? 'ok' : 'wait'", 0, got)
        QTimer.singleShot(3000, probe)

    view.setUrl(QUrl(url))
    win.show()
    app.exec()
    srv.shutdown()


def selftest():
    """CI check of the frozen exe: engine, data and the window library must load."""
    from engine.gen import generate as g
    for k in ("motor", "cutter", "military"):
        g(k, "M", "low", "dark", 1)
    from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    with open(os.path.join(app_dir(), "selftest.ok"), "w") as f:
        f.write("ok")


def main():
    if "--selftest" in sys.argv:
        try:
            selftest()
        except Exception:
            log_error(traceback.format_exc())
            sys.exit(1)
        return
    api = Api()
    if "--browser" in sys.argv:
        port = 0
        if "--port" in sys.argv:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        run_browser(api, port, "--no-open" not in sys.argv)
        return
    try:
        run_qt(api, "--guitest" in sys.argv)
    except Exception:
        # Qt could not start: log it and open the same interface as an Edge/Chrome app window
        log_error(traceback.format_exc())
        if "--guitest" in sys.argv:
            sys.exit(1)
        run_browser(api)


if __name__ == "__main__":
    main()
