# SPDX-License-Identifier: GPL-3.0-or-later
import bpy

from . import bridge
from .preferences import get_prefs

COMPOSER_UNITS = 28


def _wrap(text, width_px):
    """按像素宽度折行（中文按两个字符宽度算）"""
    units = max(16, int(width_px / (7 * bpy.context.preferences.view.ui_scale)) - 6)
    out = []
    for para in text.splitlines() or [""]:
        cur, w = "", 0
        for ch in para:
            cw = 2 if ord(ch) > 0x2E80 else 1
            if w + cw > units:
                out.append(cur)
                cur, w = "", 0
            cur += ch
            w += cw
        out.append(cur)
    return out


def _label_block(layout, text, width, icon='NONE', max_lines=12):
    col = layout.column(align=True)
    col.scale_y = 0.8
    lines = _wrap(text, width)
    for i, line in enumerate(lines[:max_lines]):
        col.label(text=line, icon=icon if i == 0 else 'BLANK1')
    if len(lines) > max_lines:
        col.label(text="…（完整内容见对话日志）", icon='BLANK1')


def draw_composer(layout, context, width, popup=False):
    """悬浮弹窗和侧边栏共用的界面"""
    r = context.window_manager.xingviz

    # 输入框
    col = layout.column()
    col.enabled = not r.busy
    col.scale_y = 1.5
    if popup and not r.busy:
        col.activate_init = True
    col.prop(r, "prompt", text="", placeholder="描述你想怎么改当前场景，例如：镜头跟随女孩，推近到耳朵特写")

    # 开关 + 发送
    row = layout.row(align=True)
    sub = row.row(align=True)
    sub.enabled = not r.busy
    sub.prop(get_prefs(), "agent", text="")
    row.prop(r, "attach_screenshot", text="截图", icon='IMAGE_DATA', toggle=True)
    row.prop(get_prefs(), "fast_mode", text="快速", icon='AUTO', toggle=True)
    on = bridge.is_running()
    row.operator("xingviz.bridge_toggle", text="桥接", icon='LINKED' if on else 'UNLINKED', depress=on)
    row.separator()
    sub = row.row(align=True)
    sub.scale_x = 1.6
    if r.busy:
        sub.operator("xingviz.cancel", text="取消", icon='CANCEL')
    else:
        sub.operator("xingviz.send", text="发送", icon='PLAY')

    # 状态
    if on and not r.busy:
        layout.label(text=f"桥接中 127.0.0.1:{bridge.port()} · 已处理 {bridge.stats['requests']} 个请求",
                     icon='CHECKMARK')
    if r.busy and popup:
        # 弹窗不会自动刷新，别显示会"卡住"的秒数
        _label_block(layout, "AI 正在工作。可以关掉这个窗口，进度和结果会显示在底部按钮上，完成后再点开查看。",
                     width, 'SORTTIME', 3)
    elif r.status:
        icon = 'SORTTIME' if r.busy else ('ERROR' if r.last_error else 'CHECKMARK')
        layout.label(text=r.status, icon=icon)
    if r.busy and r.activity and not popup:
        _label_block(layout, r.activity, width, 'TOOL_SETTINGS', 3)
    if r.last_reply and not r.busy:
        _label_block(layout.box(), r.last_reply, width, 'LIGHT', 8 if popup else 12)
    if r.last_error and not r.busy:
        _label_block(layout.box(), r.last_error.strip().splitlines()[-1], width, 'ERROR', 4)

    row = layout.row(align=True)
    row.enabled = not r.busy
    row.operator("xingviz.undo", text="撤销", icon='LOOP_BACK')
    row.operator("xingviz.new_session", text="新对话", icon='ADD')
    row.operator("xingviz.show_log", text="日志", icon='TEXT')


class XINGVIZ_PT_composer(bpy.types.Panel):
    """点击悬浮按钮弹出的输入框"""
    bl_label = "XingViz"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_ui_units_x = COMPOSER_UNITS

    def draw(self, context):
        self.layout.label(text="XingViz 星视", icon='OUTLINER_OB_CAMERA')
        width = COMPOSER_UNITS * 20 * context.preferences.view.ui_scale
        draw_composer(self.layout, context, width, popup=True)


class XINGVIZ_PT_main(bpy.types.Panel):
    bl_label = "XingViz"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "XingViz"

    def draw(self, context):
        draw_composer(self.layout, context, context.region.width)


_classes = (XINGVIZ_PT_composer, XINGVIZ_PT_main)


def register():
    for c in _classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
