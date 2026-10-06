# SPDX-License-Identifier: GPL-3.0-or-later
"""XingViz: 用自然语言通过 Claude Code 修改 Blender previz。"""

import bpy

from . import bridge, core, operators, overlay, panel, preferences, properties

_modules = (preferences, properties, operators, panel, overlay)


def register():
    for m in _modules:
        m.register()
    if preferences.get_prefs().bridge_autostart:
        bpy.app.timers.register(lambda: bridge.start(preferences.get_prefs().bridge_port) and None,
                                first_interval=1.0)


def unregister():
    bridge.stop()
    core.shutdown()
    for m in reversed(_modules):
        m.unregister()
