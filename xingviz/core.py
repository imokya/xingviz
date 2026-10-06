# SPDX-License-Identifier: GPL-3.0-or-later
"""请求流程：
   用户需求 + 场景概况 -> 后台线程运行 AI 命令行（Claude Code / Codex，见 agents.py）
   -> AI 通过桥接（xvctl.py）在当前 Blender 里查询、执行代码、截图检查
   -> 结束后记一步撤销，Cmd/Ctrl+Z 可回到修改前。
"""
import json
import re
import os
import queue
import shlex
import shutil
import subprocess
import sys
import threading
import time
import traceback

import bpy

from . import bridge
from . import agents
from .preferences import HOME_DIR, extra_path_dirs, get_prefs

LOG_TEXT = "XingViz Log"
NOTES_TEXT = "XingViz Notes"
WORK_DIR = os.path.join(HOME_DIR, "work")
XVCTL = os.path.join(HOME_DIR, "xvctl.py")

SYSTEM_PROMPT = """你是 XingViz —— 运行在 Blender 插件里的 previz（预演动画）助手。用户正在 Blender {version} 里做 previz，
你的任务是直接修改用户当前打开的场景。

操控 Blender 的唯一方式是通过 shell 命令调用这个命令行工具（命令前缀必须完全一致）：
  {cli} scene                                    当前场景摘要（帧范围、当前帧、镜头标记、选中物体）
  {cli} exec -c "<python>"                       在 Blender 主线程执行 Python：bpy 已导入，print 的内容会返回，
                                                 赋值给 _result 的值会以 JSON 返回；多次调用之间变量会保留
  {cli} exec -f {work}/step.py                   执行文件里的多行代码（推荐：先把代码写进这个文件）
  {cli} shot --frame N -o {work}/sN.png          用场景相机渲染第 N 帧，然后{view}查看图片
  {cli} shot --mode area -o {work}/view.png      截取 3D 视口当前画面

做法：
1. 先用 exec 查询，弄清相关物体、层级、动画、相机、时间轴标记，不要凭猜测修改。
2. 做有针对性的修改：只动完成需求所需的内容，不要删除或重建无关的东西，沿用场景已有的命名风格。
3. 改完用 shot 渲染一两个关键帧，看图确认效果；不对就继续调整。

效率（很重要，用户在等）：
- [XingViz 上下文] 里已经有场景地图和场景笔记，先利用它们，不要重复查询已知信息。
- 把多个查询合并到一次 exec 里，减少来回。不要为了了解动画逐帧 frame_set 采样（很慢），直接读 F 曲线关键帧。
- 修改逐帧烘焙的动画时，先删掉该帧范围内的旧关键帧，再只写关键姿态的关键帧，让插值补中间帧。

场景笔记：
- bpy.data.texts["{notes}"] 保存这个场景的结构知识，每次请求都会自动附带给你。
- 如果你弄清了对以后修改有用的信息（角色层级、关键物体、镜头实现方式、动画是否逐帧烘焙等），
  结束前用 exec 创建或更新它：30 行以内，只写事实，不写这次改了什么。

规则：
- 动画用 keyframe_insert。Blender 4.4+/5.x 的动作是分层的，不要访问 action.fcurves；
  需要 F 曲线时用 action.layers[0].strips[0].channelbag(obj.animation_data.action_slot).fcurves。
- 不要保存或打开文件（不要调用 save_mainfile / open_mainfile），不要退出 Blender，不要运行与 Blender 无关的命令。
- 用户消息开头的 [XingViz 上下文] 是插件自动附带的当前状态，用它理解「这个镜头」「这个人」之类的指代。
- 如果用户只是提问，可以只查询不修改。
- 最后用用户的语言回复 1–3 句话，说明改了什么（涉及镜头或帧号时写清楚）。"""


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


def undo_push(message):
    win = _window()
    try:
        if win:
            with bpy.context.temp_override(window=win, screen=win.screen):
                bpy.ops.ed.undo_push(message=message)
        else:
            bpy.ops.ed.undo_push(message=message)
    except Exception as ex:
        print("XingViz: undo_push failed:", ex)


def undo():
    win = _window()
    with bpy.context.temp_override(window=win, screen=win.screen):
        bpy.ops.ed.undo()


def _groups(objs, limit):
    """把 Ped_1..Ped_44 这类同名序列折叠成 Ped_#×44"""
    groups = {}
    for o in objs:
        groups.setdefault(re.sub(r"\d+", "#", o.name), []).append(o)
    items = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    parts = [f"{v[0].name}({v[0].type})" if len(v) == 1 else f"{k}×{len(v)}" for k, v in items[:limit]]
    return ", ".join(parts) + (" …" if len(items) > limit else "")


def _anim_range(o):
    ad = o.animation_data
    if ad and ad.action:
        r = ad.action.frame_range
        return f"{int(r[0])}-{int(r[1])}"
    return ""


def gather_context():
    scn = _window_scene()
    f = scn.frame_current
    lines = [
        "[XingViz 上下文]",
        f"- Blender {bpy.app.version_string}，文件：{bpy.data.filepath or '（未保存）'}",
        f"- 当前场景: {scn.name}，帧范围 {scn.frame_start}-{scn.frame_end} @ {scn.render.fps}fps，当前帧 {f}",
        f"- 活动相机: {scn.camera.name if scn.camera else '无'}",
    ]

    # 镜头表
    shots = sorted((m for m in scn.timeline_markers if m.camera), key=lambda m: m.frame)
    if shots:
        lines.append("- 镜头表（时间轴标记绑定相机）：")
        for i, m in enumerate(shots):
            end = shots[i + 1].frame - 1 if i + 1 < len(shots) else scn.frame_end
            cam = m.camera
            anim = _anim_range(cam)
            cur = " ← 当前" if m.frame <= f <= end else ""
            lines.append(f"    {m.frame}-{end} 「{m.name}」 {cam.name} {cam.data.lens:.0f}mm"
                         + (f"，动画 {anim}" if anim else "，静止") + cur)
    others = [m for m in scn.timeline_markers if not m.camera]
    if others:
        lines.append("- 其它标记: " + "；".join(f"{m.frame} {m.name}" for m in sorted(others, key=lambda m: m.frame)))
    cams = [o for o in scn.objects if o.type == 'CAMERA' and o not in {m.camera for m in shots}]
    if cams:
        lines.append("- 其它相机: " + ", ".join(o.name for o in cams[:10]))

    # 场景地图
    objs = list(scn.objects)
    tops = [o for o in objs if o.parent is None]
    lines.append(f"- 场景共 {len(objs)} 个物体；顶层: {_groups(tops, 30)}")
    rigs = sorted((o for o in tops if len(o.children_recursive) >= 5),
                  key=lambda o: -len(o.children_recursive))[:8]
    if rigs:
        lines.append("- 层级较深的物体: " + ", ".join(
            f"{o.name}（{len(o.children_recursive)} 个子物体，动画 {_anim_range(o) or '无'}）" for o in rigs))
    animated = [o for o in objs if o.animation_data and o.animation_data.action]
    if animated:
        lines.append(f"- 有动画的物体 {len(animated)} 个: {_groups(animated, 25)}")

    sel = [o.name for o in getattr(bpy.context, "selected_objects", [])][:20]
    if sel:
        lines.append("- 选中物体: " + ", ".join(sel))
    vl = bpy.context.view_layer
    act = vl.objects.active if vl else None
    if act:
        loc = act.matrix_world.translation
        lines.append(f"- 活动物体: {act.name} 位于 ({loc.x:.2f}, {loc.y:.2f}, {loc.z:.2f})")

    notes = bpy.data.texts.get(NOTES_TEXT)
    if notes and notes.as_string().strip():
        lines.append(f"- 场景笔记（{NOTES_TEXT}，之前整理的）：\n" + notes.as_string().strip()[:3000])
    else:
        lines.append(f"- 场景笔记：还没有（请在弄清场景结构后写入 bpy.data.texts[\"{NOTES_TEXT}\"]）")
    return "\n".join(lines)


def take_screenshot():
    win = _window()
    if not win:
        return ""
    area = next((a for a in win.screen.areas if a.type == 'VIEW_3D'), None)
    if not area:
        return ""
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    out = os.path.join(WORK_DIR, "viewport.png")
    try:
        with bpy.context.temp_override(window=win, screen=win.screen, area=area, region=region):
            bpy.ops.screen.screenshot_area(filepath=out)
        return out
    except Exception as ex:
        print("XingViz: screenshot failed:", ex)
        return ""


def install_client():
    """把桥接客户端放到固定路径，返回 AI 调用它的命令前缀"""
    os.makedirs(WORK_DIR, exist_ok=True)
    shutil.copy2(os.path.join(os.path.dirname(__file__), "xvctl.py"), XVCTL)
    return f"{_shell_path(sys.executable)} {_shell_path(XVCTL)}"


def _shell_path(p):
    """转成 shell 里能直接用的路径。
    Windows 上 Blender 常装在 C:\\Program Files 下：换成不含空格的 8.3 短路径，再改用正斜杠（Git Bash）"""
    if os.name == "nt":
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(p, buf, len(buf)):
            p = buf.value
        return p.replace("\\", "/")
    return shlex.quote(p)


# ------------------------------------------------------------------ AI process

class Job:
    def __init__(self, cmd, stdin_text, cwd, env, parser, name):
        self.q = queue.Queue()
        self.proc = None
        self.cancelled = False
        self.t0 = time.time()
        self.parser, self.name = parser, name
        threading.Thread(target=self._run, args=(cmd, stdin_text, cwd, env), daemon=True).start()

    def _run(self, cmd, stdin_text, cwd, env):
        other = []
        got_result = False
        try:
            self.proc = subprocess.Popen(
                cmd, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
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
                if not isinstance(d, dict):
                    continue
                for ev in self.parser.feed(d):
                    got_result |= ev[0] == "result"
                    self.q.put(ev)
            self.proc.wait()
            if not got_result and not self.cancelled:
                msg = getattr(self.parser, "error", "") or "\n".join(other[-8:]) \
                    or f"{self.name} 退出码 {self.proc.returncode}"
                self.q.put(("error", msg))
        except Exception as ex:
            self.q.put(("error", f"无法启动 {self.name}：{ex}"))
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


def start_request(prompt, screenshot=False):
    """返回 None 表示已开始，否则返回错误信息"""
    global _job, _req
    if _job:
        return "XingViz 正在处理上一个请求"
    prefs = get_prefs()
    ag = agents.current(prefs)
    exe = ag.find(prefs)
    if not exe:
        return f"找不到 {ag.label}。{ag.install_hint}；已经装了的话，在插件设置里指定程序路径"
    if prefs.auth == 'API' and not getattr(prefs, f"{ag.key}_api_key"):
        return "已选择 API Key 登录，但还没填写 API Key（插件设置里）"

    temp_bridge = not bridge.is_running()
    if temp_bridge:
        err = bridge.start(prefs.bridge_port)
        if err:
            return err
    cli = install_client()

    msg = gather_context()
    msg += f"\n\n[用户需求]\n{prompt}"
    image = take_screenshot() if screenshot else ""

    system = SYSTEM_PROMPT.format(version=bpy.app.version_string, cli=cli, work=WORK_DIR,
                                  notes=NOTES_TEXT, view=ag.view_hint)
    if prefs.extra_instructions:
        system += "\n\n用户的额外要求：" + prefs.extra_instructions
    scn = _window_scene().xingviz
    # 换了 AI 就不能接着之前的对话
    session = scn.session_id if scn.session_agent == ag.key else ""
    scn.session_agent = ag.key
    cmd, stdin_text = ag.command(exe, prefs, cli=cli, system=system, message=msg, session=session, image=image)

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([os.path.dirname(exe), *extra_path_dirs(), env.get("PATH", "")])
    ag.env(prefs, env)

    undo_push("XingViz 修改前")
    _req = dict(prompt=prompt, temp_bridge=temp_bridge, timeout=False, agent=ag)
    _job = Job(cmd, stdin_text, WORK_DIR, env, ag.Parser(), ag.label)

    r = rt()
    r.busy = True
    r.status, r.activity, r.last_error, r.last_reply = f"启动 {ag.label}…", "", "", ""
    log(f"\n## {time.strftime('%Y-%m-%d %H:%M:%S')}\n> {prompt}")
    if not bpy.app.timers.is_registered(_poll):
        bpy.app.timers.register(_poll, first_interval=0.3, persistent=True)
    redraw()
    return None


def cancel():
    if _job:
        _job.cancel()


def reset_session():
    _window_scene().xingviz.session_id = ""


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
            elif kind == "session":
                # 一开始就记下对话 ID：即使取消，下次也能接着之前查到的信息继续
                _window_scene().xingviz.session_id = val
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
                return None
    except queue.Empty:
        pass
    r.status = f"正在工作… {int(time.time() - job.t0)}s"
    redraw()
    return 0.3


def _finish(job):
    r = rt()
    if _req.get("temp_bridge"):
        bridge.stop()
    undo_push("XingViz: " + _req["prompt"][:40])
    if job.cancelled:
        r.status = "已超时" if _req.get("timeout") else "已取消"
        r.last_error = "（已做的修改可以用「撤销」回退）"
        return
    res = _req.get("result")
    if not res:
        return _fail(_req.get("error", "未知错误"))
    text = (res.get("text") or "").strip()
    if res.get("is_error"):
        ag, low = _req["agent"], text.lower()
        if any(k in low for k in ("login", "unauthorized", "401", "api key", "authentication")):
            if get_prefs().auth == 'API':
                text += "\n→ 请检查插件设置里的 API Key 和 API 地址。"
            else:
                text += f"\n→ 还没登录：打开终端（Windows 用 PowerShell），{ag.login_hint}，然后回来重新发送。"
        elif any(k in low for k in ("conversation", "session", "thread")) and ("not found" in low or "no " in low):
            reset_session()
            text += "\n→ 已重置对话，请再发送一次。"
        return _fail(text)
    r.last_reply = text
    r.status = "✓ 完成"
    log(text)


def _fail(msg):
    r = rt()
    r.status = "出错了"
    r.last_error = msg
    log(f"[错误] {msg}")
