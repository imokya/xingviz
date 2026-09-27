# XingViz previz 脚本模板
# 整个 previz 场景都由这个脚本生成。XingViz 会让 Claude 修改它，然后重新执行。
# 约定：可重复执行（每次删掉旧场景重建）；可调参数放在顶部。

import bpy
import math

SCENE_NAME = "XingViz_Previz"
FPS, END = 24, 120

# ---------------------------------------------------------------- 重建场景
tmp = bpy.data.scenes.new(SCENE_NAME + "_tmp")
if bpy.context.window:
    bpy.context.window.scene = tmp
old = bpy.data.scenes.get(SCENE_NAME)
if old:
    for o in list(old.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.scenes.remove(old)
scn = tmp
scn.name = SCENE_NAME
scn.render.fps = FPS
scn.frame_start, scn.frame_end = 1, END


def add(obj):
    scn.collection.objects.link(obj)
    return obj


def material(name, rgb):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1)
    bsdf = m.node_tree.nodes.get("Principled BSDF") if m.node_tree else None
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    return m


def box(name, loc, size, rgb):
    me = bpy.data.meshes.new(name)
    x, y, z = (s / 2 for s in size)
    verts = [(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z), (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me.from_pydata(verts, [], faces)
    me.materials.append(material("XV_" + name, rgb))
    o = add(bpy.data.objects.new(name, me))
    o.location = loc
    return o


# ---------------------------------------------------------------- 场景内容
box("Ground", (0, 10, -0.05), (20, 40, 0.1), (0.35, 0.35, 0.35))
hero = box("Hero", (0, 0, 0.9), (0.4, 0.3, 1.8), (0.8, 0.2, 0.1))
for f, y in ((1, 0), (END, 6)):
    hero.location.y = y
    hero.keyframe_insert("location", frame=f)

sun = add(bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN')))
sun.rotation_euler = (math.radians(50), 0, math.radians(30))

cam = add(bpy.data.objects.new("CAM_Main", bpy.data.cameras.new("CAM_Main")))
cam.data.lens = 35
con = cam.constraints.new('TRACK_TO')
con.target = hero
for f, y in ((1, -5), (END, 1)):
    cam.location = (3, y, 1.8)
    cam.keyframe_insert("location", frame=f)
scn.camera = cam
scn.timeline_markers.new("S1 主镜头", frame=1).camera = cam
