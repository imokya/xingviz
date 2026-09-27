# SPDX-License-Identifier: GPL-3.0-or-later
import os
import shutil

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty

# 从 Dock 启动的 Blender 拿不到 shell 的 PATH，所以逐个检查常见安装位置
_CANDIDATES = (
    "~/.local/bin/claude",
    "~/.claude/local/claude",
    "/opt/homebrew/bin/claude",
    "/usr/local/bin/claude",
    "~/.npm-global/bin/claude",
    "~/.volta/bin/claude",
)


def find_claude(custom=""):
    if custom:
        p = os.path.expanduser(bpy.path.abspath(custom))
        return p if os.path.isfile(p) else ""
    for c in _CANDIDATES:
        p = os.path.expanduser(c)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return shutil.which("claude") or ""


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
    timeout: IntProperty(name="超时（秒）", default=600, min=30, max=3600)
    auto_fix: BoolProperty(
        name="报错时自动让 Claude 修复",
        default=True,
    )
    max_fix: IntProperty(name="最多自动修复次数", default=2, min=0, max=5)
    review_before_run: BoolProperty(
        name="修改后先确认再运行",
        description="Claude 改完脚本后不自动重建场景，等你点「运行修改」",
        default=False,
    )
    extra_instructions: StringProperty(
        name="额外风格要求",
        description="每次请求都会附加给 Claude，例如：镜头语言偏日系、所有文字用中文命名",
    )

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "claude_path")
        found = find_claude(self.claude_path)
        col.label(text=f"检测到: {found}" if found else "未找到 claude，请安装 Claude Code 或手动指定路径",
                  icon='CHECKMARK' if found else 'ERROR')
        col.prop(self, "model")
        col.prop(self, "timeout")
        row = col.row()
        row.prop(self, "auto_fix")
        sub = row.row()
        sub.enabled = self.auto_fix
        sub.prop(self, "max_fix")
        col.prop(self, "review_before_run")
        col.prop(self, "extra_instructions")


def register():
    bpy.utils.register_class(XingVizPreferences)


def unregister():
    bpy.utils.unregister_class(XingVizPreferences)
