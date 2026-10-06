# SPDX-License-Identifier: GPL-3.0-or-later
"""3D 视图底部中央的悬浮胶囊按钮，点击弹出 XingViz 输入框。

用 2D gizmo 实现：Blender 自己负责悬停高亮和点击分发，不需要常驻的 modal。
"""
import math
import time

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from . import bridge
from .preferences import get_prefs

ACCENT = (0.42, 0.55, 1.0)


def _pill_points(x0, y0, x1, y1, seg=8):
    r = (y1 - y0) / 2
    pts = [((x0 + x1) / 2, (y0 + y1) / 2)]
    for cx, a0 in ((x1 - r, -90), (x0 + r, 90)):
        for i in range(seg + 1):
            a = math.radians(a0 + 180 * i / seg)
            pts.append((cx + r * math.cos(a), (y0 + y1) / 2 + r * math.sin(a)))
    pts.append(pts[1])
    return pts


def _draw(prim, pts, color):
    sh = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(sh, prim, {"pos": pts})
    sh.uniform_float("color", color)
    batch.draw(sh)


def _circle(cx, cy, r, color, seg=16):
    pts = [(cx, cy)] + [(cx + r * math.cos(2 * math.pi * i / seg), cy + r * math.sin(2 * math.pi * i / seg))
                        for i in range(seg + 1)]
    _draw('TRI_FAN', pts, color)


def _state():
    r = bpy.context.window_manager.xingviz
    if r.busy:
        return "思考中…" if not r.status else r.status.replace("Claude 正在工作… ", "思考中 "), (1.0, 0.7, 0.2)
    if r.last_error:
        return "出错了，点击查看", (1.0, 0.3, 0.3)
    return "说说你想怎么改", ACCENT


class XINGVIZ_GT_launcher(bpy.types.Gizmo):
    bl_idname = "XINGVIZ_GT_launcher"
    __slots__ = ("rect",)

    def setup(self):
        self.rect = (0, 0, 0, 0)

    def draw(self, context):
        s = context.preferences.system.ui_scale
        text, dot = _state()
        busy = context.window_manager.xingviz.busy
        on = bridge.is_running()

        title = "XingViz"
        blf.size(0, 13 * s)
        tw, _ = blf.dimensions(0, title)
        blf.size(0, 12 * s)
        sw, _ = blf.dimensions(0, text)
        h = 32 * s
        w = 34 * s + tw + 10 * s + sw + (26 * s if on else 0) + 18 * s
        cx = context.region.width / 2
        x0, y0 = cx - w / 2, 20 * s
        x1, y1 = x0 + w, y0 + h
        self.rect = (x0, y0, x1, y1)

        gpu.state.blend_set('ALPHA')
        pts = _pill_points(x0, y0, x1, y1)
        _draw('TRI_FAN', pts, (0.13, 0.13, 0.15, 0.96) if self.is_highlight else (0.08, 0.08, 0.1, 0.9))
        gpu.state.line_width_set(1.0)
        _draw('LINE_STRIP', pts[1:], (*ACCENT, 0.9 if self.is_highlight else 0.45))

        # 状态点：忙碌时呼吸闪烁
        a = 0.55 + 0.45 * math.sin(time.time() * 6) if busy else 1.0
        _circle(x0 + 18 * s, y0 + h / 2, 4.5 * s, (*dot, a))

        ty = y0 + h / 2 - 4.5 * s
        blf.size(0, 13 * s)
        blf.color(0, 1, 1, 1, 0.95)
        blf.position(0, x0 + 32 * s, ty, 0)
        blf.draw(0, title)
        blf.size(0, 12 * s)
        blf.color(0, 0.72, 0.74, 0.8, 0.95)
        blf.position(0, x0 + 32 * s + tw + 10 * s, ty, 0)
        blf.draw(0, text)
        if on:  # 桥接开启：右侧绿色小点
            _circle(x1 - 22 * s, y0 + h / 2, 3.5 * s, (0.3, 0.9, 0.45, 1))
        gpu.state.blend_set('NONE')

    def test_select(self, context, location):
        x, y = location
        x0, y0, x1, y1 = self.rect
        return 0 if x0 <= x <= x1 and y0 <= y <= y1 else -1


class XINGVIZ_GGT_launcher(bpy.types.GizmoGroup):
    bl_idname = "XINGVIZ_GGT_launcher"
    bl_label = "XingViz Launcher"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT', 'SHOW_MODAL_ALL'}

    @classmethod
    def poll(cls, context):
        try:
            return get_prefs().show_launcher
        except KeyError:
            return False

    def setup(self, context):
        gz = self.gizmos.new(XINGVIZ_GT_launcher.bl_idname)
        gz.target_set_operator("xingviz.composer")
        gz.use_draw_modal = True


_classes = (XINGVIZ_GT_launcher, XINGVIZ_GGT_launcher)


def register():
    for c in _classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
