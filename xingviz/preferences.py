# SPDX-License-Identifier: GPL-3.0-or-later
import os

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty

# 数据目录（桥接信息、客户端、截图），可用环境变量 XINGVIZ_HOME 改
HOME_DIR = os.environ.get("XINGVIZ_HOME") or os.path.expanduser("~/.xingviz")


def expand(p):
    return os.path.expandvars(os.path.expanduser(bpy.path.abspath(p)))


def extra_path_dirs():
    """从 Dock / 开始菜单启动的 Blender 拿不到 shell 的 PATH，补上常见目录"""
    if os.name == "nt":
        return [expand("~/.local/bin"), expand("%APPDATA%/npm")]
    return [expand("~/.local/bin"), "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]


def get_prefs():
    return bpy.context.preferences.addons[__package__].preferences


class XingVizPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    agent: EnumProperty(
        name="AI",
        items=(('CLAUDE', "Claude Code", "Anthropic 的 Claude Code"),
               ('CODEX', "Codex（ChatGPT）", "OpenAI 的 Codex，可用 ChatGPT 账号")),
        default='CLAUDE',
    )
    auth: EnumProperty(
        name="登录方式",
        items=(('LOCAL', "本机登录", "使用命令行工具里已经登录的账号（订阅用户选这个）"),
               ('API', "API Key", "使用 API Key 按量付费，或接入兼容的代理地址")),
        default='LOCAL',
    )

    claude_path: StringProperty(name="程序路径", description="留空则自动查找 claude", subtype='FILE_PATH')
    claude_api_key: StringProperty(name="API Key", subtype='PASSWORD')
    claude_api_base: StringProperty(name="API 地址", description="可选。用代理或兼容服务时填写，否则留空")
    model: StringProperty(name="模型", description="例如 opus、sonnet；留空使用默认模型")
    fast_model: StringProperty(name="快速模式模型", default="sonnet")

    codex_path: StringProperty(name="程序路径", description="留空则自动查找 codex", subtype='FILE_PATH')
    codex_api_key: StringProperty(name="API Key", subtype='PASSWORD')
    codex_api_base: StringProperty(name="API 地址", description="可选。用代理或兼容服务时填写，否则留空")
    codex_model: StringProperty(name="模型", description="留空使用 Codex 默认模型")

    fast_mode: BoolProperty(
        name="快速模式",
        description="更快、思考更少；适合小改动。复杂的镜头设计建议关闭",
        default=False,
    )
    timeout: IntProperty(name="超时（秒）", default=900, min=30, max=3600)
    extra_instructions: StringProperty(
        name="额外要求",
        description="每次请求都会附加给 AI，例如：镜头语言偏日系、物体名用英文",
    )
    show_launcher: BoolProperty(name="在 3D 视图底部显示悬浮按钮", default=True)
    bridge_port: IntProperty(name="桥接端口", default=8765, min=1024, max=65000)
    bridge_autostart: BoolProperty(
        name="启动 Blender 时自动开启桥接",
        description="开启后，本机上的 AI 工具可以直接在这个 Blender 里执行 Python",
        default=False,
    )

    def draw(self, context):
        from .agents import current
        ag = current(self)
        p = "claude" if ag.key == "claude" else "codex"
        layout = self.layout

        box = layout.box()
        box.row().prop(self, "agent", expand=True)
        box.row().prop(self, "auth", expand=True)
        if self.auth == 'LOCAL':
            box.label(text="首次使用：" + ag.login_hint, icon='INFO')
        else:
            box.prop(self, f"{p}_api_key", text=ag.key_hint)
            box.prop(self, f"{p}_api_base")
            box.label(text="API Key 以明文保存在本机的 Blender 偏好设置里", icon='LOCKED')

        found = ag.find(self)
        col = box.column()
        col.label(text=f"已找到 {ag.label}: {found}" if found else f"未找到 {ag.label}。{ag.install_hint}",
                  icon='CHECKMARK' if found else 'ERROR')

        col = layout.column()
        col.use_property_split = True
        col.prop(self, f"{p}_path")
        col.prop(self, "model" if p == "claude" else "codex_model")
        if p == "claude":
            col.prop(self, "fast_model")
        col.prop(self, "timeout")
        col.prop(self, "extra_instructions")
        col.prop(self, "show_launcher")
        col.separator()
        col.prop(self, "bridge_port")
        col.prop(self, "bridge_autostart")


def register():
    bpy.utils.register_class(XingVizPreferences)


def unregister():
    bpy.utils.unregister_class(XingVizPreferences)
