# SPDX-License-Identifier: GPL-3.0-or-later
"""XingViz: 用自然语言通过 Claude Code 修改 Blender previz。"""

from . import preferences, properties, operators, panel, core

_modules = (preferences, properties, operators, panel)


def register():
    for m in _modules:
        m.register()


def unregister():
    core.shutdown()
    for m in reversed(_modules):
        m.unregister()
