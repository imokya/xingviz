# SPDX-License-Identifier: GPL-3.0-or-later
import os

import bpy

from . import core


def _wrap(text, region_width):
    """按区域宽度折行（中文按两个字符宽度算）"""
    units = max(16, int(region_width / (7 * bpy.context.preferences.view.ui_scale)) - 6)
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


def _label_block(layout, text, width, icon='NONE', max_lines=14):
    col = layout.column(align=True)
    col.scale_y = 0.8
    lines = _wrap(text, width)
    for i, line in enumerate(lines[:max_lines]):
        col.label(text=line, icon=icon if i == 0 else 'BLANK1')
    if len(lines) > max_lines:
        col.label(text="…（完整内容见对话日志）", icon='BLANK1')


class XINGVIZ_PT_main(bpy.types.Panel):
    bl_label = "XingViz"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "XingViz"

    def draw(self, context):
        layout = self.layout
        r = context.window_manager.xingviz
        width = context.region.width

        row = layout.row(align=True)
        row.prop(context.scene.xingviz, "script_path", text="")
        row.operator("xingviz.new_script", text="", icon='FILE_NEW')
        row.operator("xingviz.open_script", text="", icon='TEXT')

        path = core.script_path()
        if not path or not os.path.isfile(path):
            layout.label(text="选择一个 previz 脚本，或点 + 新建", icon='INFO')
            return

        box = layout.box()
        col = box.column()
        col.enabled = not r.busy
        col.prop(r, "prompt", text="", icon='OUTLINER_DATA_SPEAKER')
        row = box.row(align=True)
        if r.busy:
            row.operator("xingviz.cancel", icon='CANCEL')
        else:
            row.scale_y = 1.3
            row.operator("xingviz.send", icon='PLAY')
        box.prop(r, "attach_screenshot")

        if r.status:
            icon = 'SORTTIME' if r.busy else ('ERROR' if r.last_error else 'CHECKMARK')
            layout.label(text=r.status, icon=icon)
        if r.busy and r.activity:
            _label_block(layout, r.activity, width, 'TOOL_SETTINGS', 3)
        if r.pending_review:
            row = layout.row(align=True)
            row.operator("xingviz.run", text="运行修改", icon='PLAY')
            row.operator("xingviz.discard", icon='LOOP_BACK')
        if r.last_reply and not r.busy:
            _label_block(layout.box(), r.last_reply, width, 'LIGHT')
        if r.last_error and not r.busy:
            _label_block(layout.box(), r.last_error.strip().splitlines()[-1], width, 'ERROR', 4)

        row = layout.row(align=True)
        row.enabled = not r.busy
        row.operator("xingviz.run", icon='FILE_REFRESH')
        row.operator("xingviz.undo", text="撤销", icon='LOOP_BACK')
        row = layout.row(align=True)
        row.operator("xingviz.new_session", icon='ADD')
        row.operator("xingviz.show_log", text="日志", icon='TEXT')


class XINGVIZ_PT_history(bpy.types.Panel):
    bl_label = "版本历史"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "XingViz"
    bl_parent_id = "XINGVIZ_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        p = core.script_path()
        return bool(p) and os.path.isfile(p)

    def draw(self, context):
        st = core.load_state(core.script_path())
        if not st["versions"]:
            self.layout.label(text="发送第一个需求后开始记录")
            return
        col = self.layout.column(align=True)
        col.enabled = not context.window_manager.xingviz.busy
        for i in range(len(st["versions"]) - 1, max(-1, len(st["versions"]) - 13), -1):
            v = st["versions"][i]
            row = col.row(align=True)
            cur = i == st["current"]
            op = row.operator("xingviz.restore", text="", icon='RADIOBUT_ON' if cur else 'RADIOBUT_OFF',
                              emboss=False)
            op.index = i
            row.label(text=f"v{i} {v['time'][-5:]}  {v['prompt']}")


_classes = (XINGVIZ_PT_main, XINGVIZ_PT_history)


def register():
    for c in _classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
