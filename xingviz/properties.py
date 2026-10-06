# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.props import BoolProperty, PointerProperty, StringProperty


class XingVizSceneProps(bpy.types.PropertyGroup):
    """随 .blend 保存"""
    session_id: StringProperty(description="Claude 对话 ID，用于连续修改时记住上下文")


class XingVizRuntimeProps(bpy.types.PropertyGroup):
    """运行时状态（不保存）"""
    prompt: StringProperty(name="需求", description="用自然语言描述你想怎么改当前的 previz")
    attach_screenshot: BoolProperty(
        name="附带视口截图",
        description="把当前 3D 视口截图发给 Claude，方便说「这个画面」",
        default=False,
    )
    busy: BoolProperty()
    status: StringProperty()
    activity: StringProperty()
    last_reply: StringProperty()
    last_error: StringProperty()


_classes = (XingVizSceneProps, XingVizRuntimeProps)


def register():
    for c in _classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.xingviz = PointerProperty(type=XingVizSceneProps)
    bpy.types.WindowManager.xingviz = PointerProperty(type=XingVizRuntimeProps)


def unregister():
    del bpy.types.WindowManager.xingviz
    del bpy.types.Scene.xingviz
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
