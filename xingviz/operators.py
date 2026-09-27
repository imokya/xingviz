# SPDX-License-Identifier: GPL-3.0-or-later
import os
import shutil

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy_extras.io_utils import ExportHelper

from . import core

TEMPLATE = os.path.join(os.path.dirname(__file__), "templates", "blank_previz.py")


def _need_script(self):
    path = core.script_path()
    if not path or not os.path.isfile(path):
        self.report({'ERROR'}, "请先选择或新建一个 previz 脚本")
        return ""
    return path


class XINGVIZ_OT_send(bpy.types.Operator):
    bl_idname = "xingviz.send"
    bl_label = "发送"
    bl_description = "把需求发给 Claude，修改 previz 脚本并重建场景"

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


class XINGVIZ_OT_ask(bpy.types.Operator):
    bl_idname = "xingviz.ask"
    bl_label = "XingViz：告诉 Claude 怎么改"
    bl_description = "弹出对话框输入需求"

    prompt: StringProperty(name="", options={'SKIP_SAVE'})
    screenshot: BoolProperty(name="附带视口截图", default=False)

    def invoke(self, context, event):
        if core.is_busy():
            self.report({'WARNING'}, "XingViz 正在处理上一个请求")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=620, confirm_text="发送")

    def draw(self, context):
        col = self.layout.column()
        col.label(text=f"脚本：{os.path.basename(core.script_path()) or '（未选择）'}", icon='FILE_SCRIPT')
        col.prop(self, "prompt", text="")
        col.prop(self, "screenshot")

    def execute(self, context):
        if not self.prompt.strip():
            return {'CANCELLED'}
        err = core.start_request(self.prompt.strip(), screenshot=self.screenshot)
        if err:
            self.report({'ERROR'}, err)
            return {'CANCELLED'}
        return {'FINISHED'}


class XINGVIZ_OT_cancel(bpy.types.Operator):
    bl_idname = "xingviz.cancel"
    bl_label = "取消"

    def execute(self, context):
        core.cancel()
        return {'FINISHED'}


class XINGVIZ_OT_run(bpy.types.Operator):
    bl_idname = "xingviz.run"
    bl_label = "重建场景"
    bl_description = "重新执行 previz 脚本（报错时按设置自动修复）"

    def execute(self, context):
        path = _need_script(self)
        if not path or core.is_busy():
            return {'CANCELLED'}
        ok = core.run_and_fix(path)
        self.report({'INFO'} if ok else {'WARNING'}, context.window_manager.xingviz.status)
        return {'FINISHED'}


class XINGVIZ_OT_discard(bpy.types.Operator):
    bl_idname = "xingviz.discard"
    bl_label = "放弃修改"
    bl_description = "把脚本恢复到上一版，不运行"

    def execute(self, context):
        path = _need_script(self)
        if not path:
            return {'CANCELLED'}
        st = core.load_state(path)
        if st["current"] > 0:
            core.restore_version(path, st["current"] - 1)
        r = context.window_manager.xingviz
        r.pending_review = False
        r.status = "已放弃修改"
        return {'FINISHED'}


class XINGVIZ_OT_undo(bpy.types.Operator):
    bl_idname = "xingviz.undo"
    bl_label = "撤销上一版"
    bl_description = "恢复脚本的上一个版本并重建场景"

    def execute(self, context):
        path = _need_script(self)
        if not path or core.is_busy():
            return {'CANCELLED'}
        st = core.load_state(path)
        if st["current"] <= 0:
            self.report({'INFO'}, "已经是最早的版本")
            return {'CANCELLED'}
        core.restore_version(path, st["current"] - 1)
        core.run_and_fix(path, fix_count=99)
        return {'FINISHED'}


class XINGVIZ_OT_restore(bpy.types.Operator):
    bl_idname = "xingviz.restore"
    bl_label = "恢复到此版本"

    index: IntProperty()

    def execute(self, context):
        path = _need_script(self)
        if not path or core.is_busy():
            return {'CANCELLED'}
        core.restore_version(path, self.index)
        core.run_and_fix(path, fix_count=99)
        return {'FINISHED'}


class XINGVIZ_OT_new_session(bpy.types.Operator):
    bl_idname = "xingviz.new_session"
    bl_label = "新对话"
    bl_description = "让 Claude 忘掉之前的对话（脚本和版本历史不受影响）"

    def execute(self, context):
        path = _need_script(self)
        if not path:
            return {'CANCELLED'}
        core.reset_session(path)
        context.window_manager.xingviz.last_reply = ""
        self.report({'INFO'}, "已开始新对话")
        return {'FINISHED'}


class XINGVIZ_OT_new_script(bpy.types.Operator, ExportHelper):
    bl_idname = "xingviz.new_script"
    bl_label = "新建 Previz 脚本"
    bl_description = "从模板新建一个 previz 脚本并生成场景"

    filename_ext = ".py"
    filter_glob: StringProperty(default="*.py", options={'HIDDEN'})

    def invoke(self, context, event):
        self.filepath = os.path.join(os.path.dirname(bpy.data.filepath) or os.path.expanduser("~"),
                                     "previz.py")
        return super().invoke(context, event)

    def execute(self, context):
        if os.path.exists(self.filepath):
            self.report({'ERROR'}, "文件已存在，请换一个名字，或直接在面板里选择它")
            return {'CANCELLED'}
        shutil.copy2(TEMPLATE, self.filepath)
        context.scene.xingviz.script_path = self.filepath
        core.run_and_fix(self.filepath, fix_count=99)
        return {'FINISHED'}


class XINGVIZ_OT_open_script(bpy.types.Operator):
    bl_idname = "xingviz.open_script"
    bl_label = "用编辑器打开脚本"

    def execute(self, context):
        path = _need_script(self)
        if path:
            bpy.ops.wm.path_open(filepath=path)
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


_classes = (XINGVIZ_OT_send, XINGVIZ_OT_ask, XINGVIZ_OT_cancel, XINGVIZ_OT_run, XINGVIZ_OT_discard,
            XINGVIZ_OT_undo, XINGVIZ_OT_restore, XINGVIZ_OT_new_session, XINGVIZ_OT_new_script,
            XINGVIZ_OT_open_script, XINGVIZ_OT_show_log)
_keymaps = []


def register():
    for c in _classes:
        bpy.utils.register_class(c)
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="3D View", space_type='VIEW_3D')
        _keymaps.append((km, km.keymap_items.new(XINGVIZ_OT_ask.bl_idname, 'X', 'PRESS', ctrl=True, shift=True)))


def unregister():
    for km, kmi in _keymaps:
        km.keymap_items.remove(kmi)
    _keymaps.clear()
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
