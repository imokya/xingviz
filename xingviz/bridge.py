# SPDX-License-Identifier: GPL-3.0-or-later
"""桥接模式：在 127.0.0.1 上开一个小 HTTP 服务，让外部的 Claude Code 会话操控正在运行的 Blender。

- 只监听本机；每个请求都要带随机令牌（X-XingViz-Token），带 Origin 头的请求（浏览器）一律拒绝
- 端口和令牌写在 ~/.xingviz/bridge.json（权限 600），xvctl.py 会读取它；目录可用环境变量 XINGVIZ_HOME 改
- HTTP 线程只负责收发，所有 bpy 操作都通过定时器在主线程执行
"""
import contextlib
import io
import json
import os
import queue
import secrets
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import bpy

from . import core
from .preferences import HOME_DIR

INFO_FILE = os.path.join(HOME_DIR, "bridge.json")

_server = None
_token = ""
_calls = queue.Queue()
_ns = {}          # exec 的命名空间在多次调用之间保留
stats = {"requests": 0, "last": ""}


# ------------------------------------------------------------------ routes (主线程)

def _override():
    win = core._window()
    return bpy.context.temp_override(window=win, screen=win.screen) if win else contextlib.nullcontext()


def r_ping(**kw):
    scn = core._window_scene()
    return {"ok": True, "blender": bpy.app.version_string, "file": bpy.data.filepath,
            "scene": scn.name, "frame": scn.frame_current}


def r_exec(code="", **kw):
    buf = io.StringIO()
    _ns.setdefault("bpy", bpy)
    _ns.pop("_result", None)
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf), _override():
            exec(compile(code, "<xingviz-bridge>", "exec"), _ns)
        return {"ok": True, "stdout": buf.getvalue(), "result": _ns.get("_result")}
    except Exception:
        return {"ok": False, "stdout": buf.getvalue(), "error": traceback.format_exc()}


def r_scene(**kw):
    return {"ok": True, "context": core.gather_context()}


def r_screenshot(path="", mode="camera", frame=None, width=960, **kw):
    """mode=camera: 用场景相机做视口渲染；mode=area: 截取 3D 视口原样画面"""
    win = core._window()
    if not win:
        return {"ok": False, "error": "没有可用的 Blender 窗口"}
    scn = win.scene
    if frame is not None:
        scn.frame_set(int(frame))
    areas = [a for a in win.screen.areas if a.type == 'VIEW_3D']
    if not areas:
        return {"ok": False, "error": "当前工作区没有 3D 视图"}
    area = max(areas, key=lambda a: a.width * a.height)
    region = next(r for r in area.regions if r.type == 'WINDOW')
    path = path or os.path.join(tempfile.gettempdir(), "xingviz_shot.png")
    with bpy.context.temp_override(window=win, screen=win.screen, area=area, region=region):
        if mode == "area":
            bpy.ops.screen.screenshot_area(filepath=path)
        else:
            if not scn.camera:
                return {"ok": False, "error": "场景没有活动相机"}
            r = scn.render
            old = r.resolution_percentage
            r.resolution_percentage = max(1, min(100, int(width * 100 / r.resolution_x)))
            try:
                bpy.ops.render.opengl(write_still=False, view_context=False)
                bpy.data.images["Render Result"].save_render(path, scene=scn)
            finally:
                r.resolution_percentage = old
    return {"ok": True, "path": path, "frame": scn.frame_current,
            "camera": scn.camera.name if scn.camera else ""}


ROUTES = {"ping": r_ping, "exec": r_exec, "scene": r_scene, "screenshot": r_screenshot}


# ------------------------------------------------------------------ plumbing

class _Call:
    def __init__(self, fn, args):
        self.fn, self.args = fn, args
        self.done = threading.Event()
        self.result = None


def _pump():
    if _server is None:
        return None
    while True:
        try:
            c = _calls.get_nowait()
        except queue.Empty:
            break
        try:
            c.result = c.fn(**c.args)
        except Exception:
            c.result = {"ok": False, "error": traceback.format_exc()}
        c.done.set()
        core.redraw()
    return 0.05


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.headers.get("Origin") or not secrets.compare_digest(
                self.headers.get("X-XingViz-Token", ""), _token):
            return self._send(403, {"ok": False, "error": "forbidden"})
        fn = ROUTES.get(self.path.strip("/"))
        if not fn:
            return self._send(404, {"ok": False, "error": f"unknown route, try: {', '.join(ROUTES)}"})
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except ValueError:
            return self._send(400, {"ok": False, "error": "bad json"})
        timeout = float(data.pop("timeout", 120))
        c = _Call(fn, data)
        _calls.put(c)
        stats["requests"] += 1
        stats["last"] = f"{time.strftime('%H:%M:%S')} {self.path.strip('/')}"
        if not c.done.wait(timeout):
            return self._send(504, {"ok": False, "error": "Blender 主线程繁忙，请求超时"})
        self._send(200, c.result)


def is_running():
    return _server is not None


def port():
    return _server.server_address[1] if _server else 0


def start(preferred_port=8765):
    global _server, _token
    if _server:
        return None
    last_err = None
    for p in range(preferred_port, preferred_port + 10):
        try:
            _server = ThreadingHTTPServer(("127.0.0.1", p), _Handler)
            break
        except OSError as ex:
            last_err = ex
    if not _server:
        return f"无法监听端口：{last_err}"
    _server.daemon_threads = True
    _token = secrets.token_urlsafe(24)
    threading.Thread(target=_server.serve_forever, daemon=True).start()
    os.makedirs(os.path.dirname(INFO_FILE), exist_ok=True)
    fd = os.open(INFO_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump({"port": port(), "token": _token, "pid": os.getpid(),
                   "blender": bpy.app.version_string}, fh)
    if not bpy.app.timers.is_registered(_pump):
        bpy.app.timers.register(_pump, first_interval=0.05, persistent=True)
    return None


def stop():
    global _server
    if not _server:
        return
    srv, _server = _server, None
    srv.shutdown()
    srv.server_close()
    while not _calls.empty():
        c = _calls.get_nowait()
        c.result = {"ok": False, "error": "桥接已关闭"}
        c.done.set()
    try:
        with open(INFO_FILE, encoding="utf-8") as fh:
            if json.load(fh).get("pid") == os.getpid():
                os.remove(INFO_FILE)
    except (OSError, ValueError):
        pass
    if bpy.app.timers.is_registered(_pump):
        bpy.app.timers.unregister(_pump)
