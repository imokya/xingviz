# SPDX-License-Identifier: GPL-3.0-or-later
import bpy

from . import bridge, core
from .preferences import get_prefs


class XINGVIZ_OT_composer(bpy.types.Operator):
    bl_idname = "xingviz.composer"
    bl_label = "XingViz"
    bl_description = "打开 XingViz 输入框"

    def invoke(self, context, event):
        bpy.ops.wm.call_panel(name="XINGVIZ_PT_composer", keep_open=True)
        return {'FINISHED'}

    def execute(self, context):
        return self.invoke(context, None)


class XINGVIZ_OT_send(bpy.types.Operator):
    bl_idname = "xingviz.send"
    bl_label = "发送"
    bl_description = "让 AI 按你的描述直接修改当前场景"

    def execute(self, context):
        r = context.window_manager.xingviz
        prompt = r.prompt.strip()
        if not prompt:
            self.report({'WARNING'}, "请先输入需求")
            return {'CANCELLED'}
        err = core.start_request(prompt, screenshot=r.attach_screenshot)
        if err:
            self.report({'ERROR'}, err)
            return {'CANCELLED'}
        r.prompt = ""
        return {'FINISHED'}


class XINGVIZ_OT_cancel(bpy.types.Operator):
    bl_idname = "xingviz.cancel"
    bl_label = "取消"

    def execute(self, context):
        core.cancel()
        return {'FINISHED'}


class XINGVIZ_OT_undo(bpy.types.Operator):
    bl_idname = "xingviz.undo"
    bl_label = "撤销"
    bl_description = "撤销 AI 的上一次修改（等同 Cmd/Ctrl+Z）"

    @classmethod
    def poll(cls, context):
        return not core.is_busy()

    def execute(self, context):
        try:
            core.undo()
        except RuntimeError as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        context.window_manager.xingviz.status = "已撤销"
        return {'FINISHED'}


class XINGVIZ_OT_new_session(bpy.types.Operator):
    bl_idname = "xingviz.new_session"
    bl_label = "新对话"
    bl_description = "让 AI 忘掉之前的对话（场景不受影响）"

    def execute(self, context):
        core.reset_session()
        r = context.window_manager.xingviz
        r.last_reply = r.last_error = r.status = ""
        self.report({'INFO'}, "已开始新对话")
        return {'FINISHED'}


class XINGVIZ_OT_show_log(bpy.types.Operator):
    bl_idname = "xingviz.show_log"
    bl_label = "查看对话日志"

    def execute(self, context):
        text = bpy.data.texts.get(core.LOG_TEXT)
        if not text:
            self.report({'INFO'}, "还没有日志")
            return {'CANCELLED'}
        for area in context.screen.areas:
            if area.type == 'TEXT_EDITOR':
                area.spaces.active.text = text
                return {'FINISHED'}
        self.report({'INFO'}, f"日志在文本块「{core.LOG_TEXT}」中，可在 Scripting 工作区的文本编辑器查看")
        return {'FINISHED'}


class XINGVIZ_OT_bridge_toggle(bpy.types.Operator):
    bl_idname = "xingviz.bridge_toggle"
    bl_label = "开关桥接"
    bl_description = "常开桥接：允许本机其它 AI 工具（Claude Code、Codex 等）直接操控这个 Blender"

    def execute(self, context):
        if bridge.is_running():
            if core.is_busy():
                self.report({'WARNING'}, "AI 正在工作，需要桥接，请稍后再关")
                return {'CANCELLED'}
            bridge.stop()
            self.report({'INFO'}, "桥接已关闭")
        else:
            err = bridge.start(get_prefs().bridge_port)
            if err:
                self.report({'ERROR'}, err)
                return {'CANCELLED'}
            core.install_client()
            self.report({'INFO'}, f"桥接已开启：127.0.0.1:{bridge.port()}")
        return {'FINISHED'}


_classes = (XINGVIZ_OT_composer, XINGVIZ_OT_send, XINGVIZ_OT_cancel, XINGVIZ_OT_undo,
            XINGVIZ_OT_new_session, XINGVIZ_OT_show_log, XINGVIZ_OT_bridge_toggle)
_keymaps = []


def register():
    for c in _classes:
        bpy.utils.register_class(c)
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="3D View", space_type='VIEW_3D')
        _keymaps.append((km, km.keymap_items.new(XINGVIZ_OT_composer.bl_idname, 'X', 'PRESS', ctrl=True, shift=True)))


def unregister():
    for km, kmi in _keymaps:
        km.keymap_items.remove(kmi)
    _keymaps.clear()
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
