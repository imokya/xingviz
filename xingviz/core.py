# SPDX-License-Identifier: GPL-3.0-or-later
"""请求流程：
   用户需求 -> 后台线程运行 `claude -p`（只允许编辑脚本）-> 脚本有变化则存版本
   -> 主线程 exec 脚本重建场景 -> 报错时把 traceback 发回 Claude 自动修复。
"""
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback

import bpy

from .preferences import find_claude, get_prefs

STATE_DIRNAME = ".xingviz"
LOG_TEXT = "XingViz Log"

SYSTEM_PROMPT = """你是 XingViz —— 运行在 Blender 插件里的 previz（预演动画）助手。

工作方式：
- 用户的 previz 完全由一个 Python 脚本生成：{script}
  你只通过编辑这个文件来实现需求（必要时可以在同一目录新建辅助 .py 文件）。不要修改 .xingviz 目录。
- 你改完后，插件会在正在运行的 Blender {version} 中用 exec 重新执行整个脚本（__file__ 已设置）。所以脚本必须：
  可重复执行（先清理再重建它自己创建的场景/数据）、自包含、不依赖特定的 bpy.ops 上下文；用到 bpy.context.window / screen 时先判空。
- 你没有 Bash 权限，不要尝试运行 Blender 或其它命令。
- 做最小、有针对性的修改，保留脚本已有的结构、命名和注释风格；可调参数放在文件顶部。
- Blender 4.4+/5.x API 注意：动作是分层的，不要直接访问 action.fcurves，用 keyframe_insert；VSE 用 sequence_editor.strips；
  材质/世界直接用 node_tree（use_nodes 已弃用）。
- 用户消息开头的 [XingViz 上下文] 是插件自动附带的当前 Blender 状态（当前帧、相机、选中物体等），用它理解「这个镜头」「这个人」之类的指代。
- 如果用户只是提问、不需要改动，可以不改文件直接回答。
- 最后用用户的语言回复 1–3 句话，说明改了什么（涉及镜头/帧号时写清楚）。"""

FIX_PROMPT = """脚本在 Blender 中执行失败，错误如下：
```
{tb}
```
请修复脚本使其能正确运行，同时保持之前修改的意图。"""


# ------------------------------------------------------------------ project state

def script_path(scene=None):
    scene = scene or _window_scene()
    p = scene.xingviz.script_path if scene else ""
    return os.path.normpath(bpy.path.abspath(p)) if p else ""


def state_dir(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    d = os.path.join(os.path.dirname(path), STATE_DIRNAME, stem)
    os.makedirs(d, exist_ok=True)
    return d


def load_state(path):
    try:
        with open(os.path.join(state_dir(path), "state.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"session_id": "", "versions": [], "current": -1}


def save_state(path, st):
    with open(os.path.join(state_dir(path), "state.json"), "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False, indent=1)


def file_hash(path):
    try:
        with open(path, "rb") as fh:
            return hashlib.sha1(fh.read()).hexdigest()
    except OSError:
        return ""


def add_version(path, label):
    st = load_state(path)
    n = len(st["versions"])
    name = f"v{n:03d}.py"
    shutil.copy2(path, os.path.join(state_dir(path), name))
    st["versions"].append({"file": name, "prompt": label,
                           "time": time.strftime("%m-%d %H:%M"), "hash": file_hash(path)})
    st["current"] = n
    save_state(path, st)


def ensure_baseline(path):
    """第一次请求时存 v000；用户手动改过脚本也记一版"""
    st = load_state(path)
    cur = st["versions"][st["current"]] if st["versions"] else None
    if cur is None or cur["hash"] != file_hash(path):
        add_version(path, "（手动修改）" if cur else "（初始版本）")


def restore_version(path, index):
    st = load_state(path)
    v = st["versions"][index]
    shutil.copy2(os.path.join(state_dir(path), v["file"]), path)
    st["current"] = index
    save_state(path, st)


def reset_session(path):
    st = load_state(path)
    st["session_id"] = ""
    save_state(path, st)


# ------------------------------------------------------------------ blender helpers

def _window():
    wm = bpy.context.window_manager
    return bpy.context.window or (wm.windows[0] if wm.windows else None)


def _window_scene():
    win = _window()
    return win.scene if win else bpy.context.scene


def rt():
    return bpy.context.window_manager.xingviz


def redraw():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            area.tag_redraw()


def log(text):
    t = bpy.data.texts.get(LOG_TEXT) or bpy.data.texts.new(LOG_TEXT)
    t.from_string(t.as_string() + text + "\n")


def gather_context(path):
    scn = _window_scene()
    f = scn.frame_current
    lines = [
        "[XingViz 上下文]",
        f"- Blender {bpy.app.version_string}",
        f"- previz 脚本: {path}",
        f"- 当前场景: {scn.name}，帧范围 {scn.frame_start}-{scn.frame_end} @ {scn.render.fps}fps，当前帧 {f}",
    ]
    if scn.camera:
        lines.append(f"- 当前活动相机: {scn.camera.name}")
    markers = sorted(scn.timeline_markers, key=lambda m: m.frame)
    if markers:
        lines.append("- 时间轴标记: " + "；".join(
            f"{m.frame} {m.name}" + (f"（相机 {m.camera.name}）" if m.camera else "") for m in markers[:30]))
        shot = [m for m in markers if m.camera and m.frame <= f]
        if shot:
            lines.append(f"- 当前帧所在镜头: {shot[-1].name}")
    sel = [o.name for o in bpy.context.selected_objects][:20] if hasattr(bpy.context, "selected_objects") else []
    if sel:
        lines.append("- 选中物体: " + ", ".join(sel))
    act = bpy.context.view_layer.objects.active if bpy.context.view_layer else None
    if act:
        loc = act.matrix_world.translation
        lines.append(f"- 活动物体: {act.name} 位于 ({loc.x:.2f}, {loc.y:.2f}, {loc.z:.2f})")
    return "\n".join(lines)


def take_screenshot(path):
    win = _window()
    if not win:
        return ""
    area = next((a for a in win.screen.areas if a.type == 'VIEW_3D'), None)
    if not area:
        return ""
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    out = os.path.join(state_dir(path), "viewport.png")
    try:
        with bpy.context.temp_override(window=win, screen=win.screen, area=area, region=region):
            bpy.ops.screen.screenshot_area(filepath=out)
        return out
    except Exception as ex:
        print("XingViz: screenshot failed:", ex)
        return ""


def run_script(path):
    """在主线程执行 previz 脚本，返回 (ok, traceback)"""
    win = _window()
    scn = win.scene if win else bpy.context.scene
    frame, sp = scn.frame_current, scn.xingviz.script_path
    folder = os.path.dirname(path)
    added = folder not in sys.path
    if added:
        sys.path.insert(0, folder)
    try:
        with open(path, encoding="utf-8") as fh:
            code = compile(fh.read(), path, "exec")
        g = {"__name__": "__main__", "__file__": path}
        if win:
            with bpy.context.temp_override(window=win, screen=win.screen):
                exec(code, g)
        else:
            exec(code, g)
    except Exception:
        return False, traceback.format_exc()
    finally:
        if added and folder in sys.path:
            sys.path.remove(folder)
        # 脚本可能新建/切换了场景（即使中途报错）：把脚本路径带过去
        new = win.scene if win else bpy.context.scene
        if not new.xingviz.script_path:
            new.xingviz.script_path = sp
    new.frame_set(min(max(frame, new.frame_start), new.frame_end))
    return True, ""


# ------------------------------------------------------------------ claude process

def _describe_tool(c):
    name, inp = c.get("name", ""), c.get("input") or {}
    fp = os.path.basename(inp.get("file_path", "") or inp.get("path", ""))
    verbs = {"Read": "读取", "Edit": "修改", "Write": "写入", "Grep": "搜索", "Glob": "查找文件"}
    return f"{verbs.get(name, name)} {fp or inp.get('pattern', '')}".strip()


class Job:
    def __init__(self, cmd, stdin_text, cwd, env):
        self.q = queue.Queue()
        self.proc = None
        self.cancelled = False
        self.t0 = time.time()
        threading.Thread(target=self._run, args=(cmd, stdin_text, cwd, env), daemon=True).start()

    def _run(self, cmd, stdin_text, cwd, env):
        other = []
        got_result = False
        try:
            self.proc = subprocess.Popen(
                cmd, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
            self.proc.stdin.write(stdin_text)
            self.proc.stdin.close()
            for line in self.proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    other.append(line)
                    continue
                t = d.get("type")
                if t == "assistant":
                    for c in d.get("message", {}).get("content", []):
                        if c.get("type") == "tool_use":
                            self.q.put(("activity", _describe_tool(c)))
                        elif c.get("type") == "text" and c.get("text", "").strip():
                            self.q.put(("activity", c["text"].strip().splitlines()[0]))
                elif t == "result":
                    got_result = True
                    self.q.put(("result", d))
            self.proc.wait()
            if not got_result and not self.cancelled:
                msg = "\n".join(other[-8:]) or f"claude 退出码 {self.proc.returncode}"
                self.q.put(("error", msg))
        except Exception as ex:
            self.q.put(("error", f"无法启动 claude：{ex}"))
        finally:
            self.q.put(("done", None))

    def cancel(self):
        self.cancelled = True
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


_job = None
_req = {}


def is_busy():
    return _job is not None


def start_request(prompt, screenshot=False, is_fix=False, fix_count=0):
    """返回 None 表示已开始，否则返回错误信息"""
    global _job, _req
    if _job:
        return "XingViz 正在处理上一个请求"
    path = script_path()
    if not path or not os.path.isfile(path):
        return "请先选择或新建一个 previz 脚本"
    prefs = get_prefs()
    claude = find_claude(prefs.claude_path)
    if not claude:
        return "找不到 claude 命令，请在插件偏好设置里指定 Claude CLI 路径"

    ensure_baseline(path)
    st = load_state(path)
    msg = gather_context(path)
    if screenshot:
        shot = take_screenshot(path)
        if shot:
            msg += f"\n- 用户附带了当前 3D 视口截图：{shot}（请用 Read 查看）"
    msg += f"\n\n[用户需求]\n{prompt}"

    system = SYSTEM_PROMPT.format(script=path, version=bpy.app.version_string)
    if prefs.extra_instructions:
        system += "\n\n用户的额外要求：" + prefs.extra_instructions
    cmd = [claude, "-p", "--output-format", "stream-json", "--verbose",
           "--permission-mode", "acceptEdits",
           "--allowedTools", "Read", "Edit", "Write", "Glob", "Grep",
           "--append-system-prompt", system]
    if st.get("session_id"):
        cmd += ["--resume", st["session_id"]]
    if prefs.model:
        cmd += ["--model", prefs.model]

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([
        os.path.dirname(claude), os.path.expanduser("~/.local/bin"),
        "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", env.get("PATH", "")])

    _req = dict(path=path, prompt=prompt, is_fix=is_fix, fix_count=fix_count,
                before=file_hash(path), timeout=False)
    _job = Job(cmd, msg, os.path.dirname(path), env)

    r = rt()
    r.busy, r.pending_review = True, False
    r.status, r.activity, r.last_error = "启动 Claude Code…", "", ""
    log(f"\n## {time.strftime('%Y-%m-%d %H:%M:%S')}\n> {prompt if not is_fix else '（自动修复报错）'}")
    if not bpy.app.timers.is_registered(_poll):
        bpy.app.timers.register(_poll, first_interval=0.3, persistent=True)
    redraw()
    return None


def cancel():
    if _job:
        _job.cancel()


def shutdown():
    cancel()
    if bpy.app.timers.is_registered(_poll):
        bpy.app.timers.unregister(_poll)


def _poll():
    global _job
    job = _job
    if job is None:
        return None
    r = rt()
    if not job.cancelled and time.time() - job.t0 > get_prefs().timeout:
        _req["timeout"] = True
        job.cancel()
    try:
        while True:
            kind, val = job.q.get_nowait()
            if kind == "activity":
                r.activity = val[:160]
            elif kind == "result":
                _req["result"] = val
            elif kind == "error":
                _req["error"] = val
            elif kind == "done":
                _job = None
                try:
                    _finish(job)
                except Exception:
                    r.status = "XingViz 内部错误"
                    r.last_error = traceback.format_exc()
                    r.busy = False
                redraw()
                # _finish 可能已经发起了自动修复请求，此时继续轮询
                return 0.3 if _job is not None else None
    except queue.Empty:
        pass
    r.status = f"Claude 正在工作… {int(time.time() - job.t0)}s"
    redraw()
    return 0.3


def _fail(msg):
    r = rt()
    r.busy = False
    r.status = "出错了"
    r.last_error = msg
    log(f"[错误] {msg}")


def _finish(job):
    r = rt()
    path = _req["path"]
    if job.cancelled:
        r.busy = False
        r.status = "已超时" if _req.get("timeout") else "已取消"
        _check_changed(path, run=False)
        return
    res = _req.get("result")
    if not res:
        return _fail(_req.get("error", "未知错误"))
    text = (res.get("result") or "").strip()
    if res.get("is_error"):
        if "login" in text.lower():
            text += "\n→ 请在终端运行 claude，输入 /login 登录后再试。"
        if "conversation" in text.lower():
            reset_session(path)
            text += "\n→ 已重置对话，请再发送一次。"
        return _fail(text)

    st = load_state(path)
    st["session_id"] = res.get("session_id", "")
    save_state(path, st)
    r.last_reply = text
    log(text)
    _check_changed(path, run=True)


def _check_changed(path, run):
    r = rt()
    if file_hash(path) == _req["before"]:
        r.busy = False
        if run:
            r.status = "完成（脚本没有改动）"
        return
    label = "自动修复" if _req["is_fix"] else _req["prompt"][:60]
    add_version(path, label)
    if not run:
        return
    if get_prefs().review_before_run and not _req["is_fix"]:
        r.busy = False
        r.pending_review = True
        r.status = "脚本已修改，等待你确认运行"
        return
    run_and_fix(path, _req["fix_count"])


def run_and_fix(path, fix_count=0):
    r = rt()
    r.status = "正在重建场景…"
    r.pending_review = False
    ok, tb = run_script(path)
    if ok:
        r.busy = False
        r.status = "✓ previz 已更新"
        r.last_error = ""
        return True
    r.last_error = tb[-3000:]
    log("[脚本报错]\n" + tb)
    prefs = get_prefs()
    if prefs.auto_fix and fix_count < prefs.max_fix:
        r.busy = False
        err = start_request(FIX_PROMPT.format(tb=tb[-4000:]), is_fix=True, fix_count=fix_count + 1)
        if err is None:
            r.status = f"脚本报错，正在自动修复（第 {fix_count + 1} 次）…"
            return False
    r.busy = False
    r.status = "脚本报错"
    return False
