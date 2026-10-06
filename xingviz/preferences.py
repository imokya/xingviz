# SPDX-License-Identifier: GPL-3.0-or-later
import os
import shutil

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty

# 数据目录（桥接信息、客户端、截图），可用环境变量 XINGVIZ_HOME 改
HOME_DIR = os.environ.get("XINGVIZ_HOME") or os.path.expanduser("~/.xingviz")

# 从 Dock / 开始菜单启动的 Blender 拿不到 shell 的 PATH，所以逐个检查常见安装位置
if os.name == "nt":
    _CANDIDATES = (
        "~/.local/bin/claude.exe",
        "%APPDATA%/npm/claude.cmd",
        "%LOCALAPPDATA%/Programs/claude/claude.exe",
    )
else:
    _CANDIDATES = (
        "~/.local/bin/claude",
        "~/.claude/local/claude",
        "/opt/homebrew/bin/claude",
        "/usr/local/bin/claude",
        "~/.npm-global/bin/claude",
        "~/.volta/bin/claude",
    )


def _expand(p):
    return os.path.expandvars(os.path.expanduser(p))


def find_claude(custom=""):
    if custom:
        p = _expand(bpy.path.abspath(custom))
        return p if os.path.isfile(p) else ""
    for c in _CANDIDATES:
        p = _expand(c)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return shutil.which("claude") or ""


def claude_command(path):
    """Windows 上 npm 装的是 claude.cmd，经 cmd.exe 转发时多行参数（系统提示词）会被截断，改为直接用 node 运行"""
    if os.name == "nt" and path.lower().endswith((".cmd", ".bat")):
        cli = os.path.join(os.path.dirname(path), "node_modules", "@anthropic-ai", "claude-code", "cli.js")
        node = shutil.which("node") or os.path.join(os.path.dirname(path), "node.exe")
        if os.path.isfile(cli) and os.path.isfile(node):
            return [node, cli]
    return [path]


def extra_path_dirs():
    """补到子进程 PATH 里的常见目录"""
    if os.name == "nt":
        return [_expand("~/.local/bin"), _expand("%APPDATA%/npm")]
    return [_expand("~/.local/bin"), "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]


def get_prefs():
    return bpy.context.preferences.addons[__package__].preferences


class XingVizPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    claude_path: StringProperty(
        name="Claude CLI 路径",
        description="留空则自动查找 claude 命令",
        subtype='FILE_PATH',
    )
    model: StringProperty(
        name="模型",
        description="传给 claude --model，留空使用 Claude Code 默认模型（如 opus、sonnet）",
    )
    timeout: IntProperty(name="超时（秒）", default=900, min=30, max=3600)
    fast_mode: BoolProperty(
        name="快速模式",
        description="用更快的模型、较少思考；适合小改动。复杂的镜头设计建议关闭",
        default=False,
    )
    fast_model: StringProperty(name="快速模式模型", default="sonnet")
    show_launcher: BoolProperty(
        name="在 3D 视图底部显示悬浮按钮",
        default=True,
    )
    bridge_port: IntProperty(name="桥接端口", default=8765, min=1024, max=65000)
    bridge_autostart: BoolProperty(
        name="启动 Blender 时自动开启桥接",
        description="开启后，本机上的 Claude Code 可以直接在这个 Blender 里执行 Python",
        default=False,
    )
    extra_instructions: StringProperty(
        name="额外风格要求",
        description="每次请求都会附加给 Claude，例如：镜头语言偏日系、所有文字用中文命名",
    )

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "show_launcher")
        col.prop(self, "claude_path")
        found = find_claude(self.claude_path)
        col.label(text=f"检测到: {found}" if found else "未找到 claude，请安装 Claude Code 或手动指定路径",
                  icon='CHECKMARK' if found else 'ERROR')
        col.prop(self, "model")
        row = col.row()
        row.prop(self, "fast_mode")
        row.prop(self, "fast_model", text="")
        col.prop(self, "timeout")
        col.prop(self, "extra_instructions")
        col.separator()
        col.label(text="桥接：发送需求时会临时开启；常开则允许本机其它 Claude Code 会话操控此 Blender", icon='LINKED')
        row = col.row()
        row.prop(self, "bridge_port")
        row.prop(self, "bridge_autostart")


def register():
    bpy.utils.register_class(XingVizPreferences)


def unregister():
    bpy.utils.unregister_class(XingVizPreferences)
