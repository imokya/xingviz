# Previz: 女孩走在喧闹街道 -> 掏出耳机仓 -> 戴上耳机 -> 世界瞬间静止
# 用 XingViz 插件选择本文件即可运行 / 修改；
# 或在 Blender Python Console 中运行:
#   exec(open("/path/to/earbuds_previz.py").read())
# 可重复运行：会删除并重建 "Previz_Earbuds" 场景，不影响其它场景。

import bpy, bmesh, math, random, os
from mathutils import Vector, Euler

OUT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
SCN_NAME = "Previz_Earbuds"
FPS, END = 24, 336
FREEZE = 202          # 时间静止的帧
SPEED = 0.054         # 女孩步行速度 m/frame

# ---------------------------------------------------------------- helpers
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease(x): x = clamp(x); return x * x * (3 - 2 * x)
def lerp(a, b, t): return a + (b - a) * t

def sched(keys, f):
    """keys=[(frame,value),...]，平滑插值"""
    if f <= keys[0][0]: return keys[0][1]
    for (f0, v0), (f1, v1) in zip(keys, keys[1:]):
        if f <= f1:
            return lerp(v0, v1, ease((f - f0) / (f1 - f0)))
    return keys[-1][1]

def teff(f):
    """世界时间：FREEZE 前 6 帧急速减速，然后停住"""
    T = 6.0
    if f <= FREEZE - T: return float(f)
    u = min(f - (FREEZE - T), T)
    return (FREEZE - T) + u - u * u / (2 * T)

# ---------------------------------------------------------------- scene
prefs = bpy.context.preferences.edit
old_interp = prefs.keyframe_new_interpolation_type
prefs.keyframe_new_interpolation_type = 'LINEAR'

scn = bpy.data.scenes.new(SCN_NAME + "_tmp")
if bpy.context.window:
    bpy.context.window.scene = scn
old = bpy.data.scenes.get(SCN_NAME)
if old:
    for o in list(old.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for c in list(old.collection.children):
        bpy.data.collections.remove(c)
    bpy.data.scenes.remove(old)
scn.name = SCN_NAME
scn.render.fps = FPS
scn.frame_start, scn.frame_end = 1, END
scn.render.resolution_x, scn.render.resolution_y = 1920, 1080
try:
    scn.eevee.taa_render_samples = 32
except Exception:
    pass

col = bpy.data.collections.new("Previz")
scn.collection.children.link(col)

# ---------------------------------------------------------------- meshes / materials
MESH = {}
def get_mesh(kind):
    if kind in MESH: return MESH[kind]
    me = bpy.data.meshes.get("PV_" + kind)
    if me is None:
        me = bpy.data.meshes.new("PV_" + kind)
        bm = bmesh.new()
        if kind == 'cube':
            bmesh.ops.create_cube(bm, size=1.0)
        elif kind == 'sphere':
            bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=12, radius=0.5)
        elif kind == 'cyl':
            bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.5, radius2=0.5, depth=1.0)
        bm.to_mesh(me); bm.free()
        if kind != 'cube':
            for p in me.polygons: p.use_smooth = True
        me.materials.append(None)
    MESH[kind] = me
    return me

MATS = {}
def mat(name, rgb, emit=0.0, rough=0.6, metal=0.0, unique=False):
    if name in MATS and not unique: return MATS[name]
    m = bpy.data.materials.new("PV_" + name)
    try: m.use_nodes = True
    except Exception: pass
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = (*rgb, 1)
        b.inputs["Emission Strength"].default_value = emit
    m.diffuse_color = (*rgb, 1)
    MATS[name] = m
    return m

def obj(name, kind, loc=(0, 0, 0), scale=(1, 1, 1), m=None, parent=None, rot=(0, 0, 0)):
    o = bpy.data.objects.new(name, get_mesh(kind))
    col.objects.link(o)
    if parent: o.parent = parent
    o.location, o.scale, o.rotation_euler = loc, scale, rot
    if m:
        o.material_slots[0].link = 'OBJECT'
        o.material_slots[0].material = m
    return o

def empty(name, loc=(0, 0, 0), parent=None, size=0.1):
    o = bpy.data.objects.new(name, None)
    o.empty_display_size = size
    col.objects.link(o)
    if parent: o.parent = parent
    o.location = loc
    return o

def key(o, path, f):
    o.keyframe_insert(path, frame=f)

# palette
M = dict(
    skin=mat("skin", (0.85, 0.62, 0.5)), hair=mat("hair", (0.06, 0.04, 0.03)),
    jacket=mat("jacket", (0.78, 0.16, 0.10)), jeans=mat("jeans", (0.12, 0.18, 0.36)),
    shoe=mat("shoe", (0.92, 0.92, 0.9)), white=mat("case_white", (0.95, 0.95, 0.95), rough=0.25),
    road=mat("road", (0.07, 0.07, 0.08), rough=0.9), walk=mat("sidewalk", (0.42, 0.41, 0.39), rough=0.9),
    paint=mat("paint", (0.9, 0.9, 0.85)), glass=mat("glass", (0.08, 0.12, 0.18), emit=0.4, rough=0.1),
    pole=mat("pole", (0.15, 0.16, 0.17), metal=0.8), lamp=mat("lamp", (1.0, 0.8, 0.5), emit=6),
    trunk=mat("trunk", (0.2, 0.13, 0.08)), leafy=mat("leafy", (0.18, 0.35, 0.12)),
    tire=mat("tire", (0.02, 0.02, 0.02)), headl=mat("headlight", (1, 0.95, 0.8), emit=8),
    pigeon=mat("pigeon", (0.45, 0.46, 0.5)),
)
LED_CASE = mat("led_case", (0.1, 1.0, 0.4), unique=True)
LED_BUD = mat("led_bud", (0.1, 0.5, 1.0), unique=True)

random.seed(7)

# ================================================================ ENVIRONMENT
Y0, Y1 = -60, 110
obj("Road", 'cube', (-5.1, (Y0 + Y1) / 2, -0.2), (5.8, Y1 - Y0, 0.1), M['road'])
obj("Sidewalk_R", 'cube', (0.65, (Y0 + Y1) / 2, -0.1), (5.7, Y1 - Y0, 0.2), M['walk'])
obj("Sidewalk_L", 'cube', (-10.0, (Y0 + Y1) / 2, -0.1), (4.0, Y1 - Y0, 0.2), M['walk'])
for i, y in enumerate(range(Y0, Y1, 6)):
    obj(f"LaneDash_{i}", 'cube', (-5.1, y, -0.145), (0.15, 3, 0.01), M['paint'])
for i in range(6):
    obj(f"Zebra_{i}", 'cube', (-7.5 + i * 0.95, 24, -0.144), (0.5, 3.5, 0.01), M['paint'])

FACADES = [(0.55, 0.5, 0.45), (0.62, 0.58, 0.52), (0.35, 0.33, 0.33), (0.5, 0.36, 0.3),
           (0.7, 0.66, 0.6), (0.3, 0.35, 0.4), (0.58, 0.45, 0.35)]
NEON = [(1, 0.1, 0.5), (0.1, 0.9, 1), (1, 0.6, 0.1), (0.6, 0.2, 1), (0.2, 1, 0.4)]
bi = 0
for side, xf in ((1, 3.5), (-1, -12.0)):
    y = Y0
    while y < Y1:
        w = random.uniform(6, 12); h = random.uniform(9, 26); d = 9
        cx = xf + side * d / 2
        obj(f"Bldg_{bi}", 'cube', (cx, y + w / 2, h / 2), (d, w - 0.3, h), mat(f"facade{bi%7}", FACADES[bi % 7]))
        z = 4.5
        while z < h - 1.5:
            obj(f"Win_{bi}_{int(z)}", 'cube', (xf - side * 0.03, y + w / 2, z), (0.06, w - 1.2, 1.3), M['glass'])
            z += 3.2
        nc = NEON[bi % len(NEON)]
        obj(f"Sign_{bi}", 'cube', (xf - side * 0.3, y + w / 2, 3.0), (0.12, w * 0.55, 0.55),
            mat(f"neon{bi%5}", nc, emit=5))
        obj(f"Awning_{bi}", 'cube', (xf - side * 0.7, y + w / 2, 2.55), (1.4, w * 0.8, 0.08),
            mat(f"awning{bi%3}", [(0.5, 0.1, 0.1), (0.1, 0.25, 0.2), (0.2, 0.2, 0.25)][bi % 3]))
        y += w; bi += 1

for i, y in enumerate(range(-54, 105, 12)):
    obj(f"LampPole_{i}", 'cyl', (-1.9, y, 2.5), (0.12, 0.12, 5), M['pole'])
    obj(f"LampArm_{i}", 'cube', (-2.25, y, 4.95), (0.8, 0.08, 0.08), M['pole'])
    obj(f"LampHead_{i}", 'sphere', (-2.6, y, 4.85), (0.3, 0.3, 0.2), M['lamp'])
    obj(f"TreeTrunk_{i}", 'cyl', (-1.6, y + 6, 1.25), (0.22, 0.22, 2.5), M['trunk'])
    obj(f"TreeTop_{i}", 'sphere', (-1.6, y + 6, 3.6), (2.2, 2.2, 2.8), M['leafy'])
obj("TrafficPole", 'cyl', (-1.9, 22.3, 1.6), (0.12, 0.12, 3.2), M['pole'])
obj("TrafficBox", 'cube', (-1.9, 22.3, 3.4), (0.35, 0.3, 0.9), M['pole'])
obj("TrafficRed", 'sphere', (-1.9, 22.14, 3.65), (0.18, 0.05, 0.18), mat("red_light", (1, 0.05, 0.02), emit=10))

# ---------------------------------------------------------------- lights & world
sun_d = bpy.data.lights.new("PV_Sun", 'SUN'); sun_d.energy = 3.5; sun_d.color = (1, 0.88, 0.75)
sun_d.angle = math.radians(2)
sun = bpy.data.objects.new("Sun", sun_d); col.objects.link(sun)
sun.rotation_euler = (math.radians(55), 0, math.radians(-140))

world = bpy.data.worlds.new("PV_World"); scn.world = world
try: world.use_nodes = True
except Exception: pass
bg = world.node_tree.nodes.get("Background") if world.node_tree else None

def set_world(c, s, f):
    if bg:
        bg.inputs[0].default_value = (*c, 1); bg.inputs[1].default_value = s
        bg.inputs[0].keyframe_insert("default_value", frame=f)
        bg.inputs[1].keyframe_insert("default_value", frame=f)

set_world((0.55, 0.65, 0.82), 0.9, 1); set_world((0.55, 0.65, 0.82), 0.9, FREEZE)
set_world((0.25, 0.32, 0.5), 0.35, FREEZE + 10)
for f, e, c in ((1, 3.5, (1, 0.88, 0.75)), (FREEZE, 3.5, (1, 0.88, 0.75)), (FREEZE + 10, 0.9, (0.6, 0.72, 1.0))):
    sun_d.energy = e; sun_d.color = c
    sun_d.keyframe_insert("energy", frame=f); sun_d.keyframe_insert("color", frame=f)

# ================================================================ GIRL
root = empty("Girl_Root", size=0.4)
pelvis = empty("Girl_Pelvis", (0, 0, 0.95), root)
obj("Girl_Hips", 'sphere', (0, 0, 0), (0.30, 0.2, 0.22), M['jeans'], pelvis)
obj("Girl_Torso", 'sphere', (0, 0, 0.24), (0.32, 0.22, 0.52), M['jacket'], pelvis)
obj("Girl_Neck", 'cyl', (0, 0, 0.5), (0.07, 0.07, 0.12), M['skin'], pelvis)
head = empty("Girl_Head", (0, 0, 0.5), pelvis)
obj("Girl_Face", 'sphere', (0, 0.005, 0.1), (0.18, 0.2, 0.23), M['skin'], head)
obj("Girl_Hair", 'sphere', (0, -0.02, 0.125), (0.2, 0.2, 0.21), M['hair'], head)
obj("Girl_Ponytail", 'sphere', (0, -0.13, 0.06), (0.08, 0.1, 0.2), M['hair'], head)
obj("Girl_Nose", 'sphere', (0, 0.1, 0.09), (0.03, 0.04, 0.04), M['skin'], head)
for s in (-1, 1):
    obj(f"Girl_Eye_{'L' if s<0 else 'R'}", 'sphere', (0.04 * s, 0.092, 0.12), (0.02, 0.01, 0.02), M['hair'], head)
    obj(f"Girl_Ear_{'L' if s<0 else 'R'}", 'sphere', (0.093 * s, 0, 0.1), (0.025, 0.04, 0.05), M['skin'], head)

L1, L2, LT = 0.28, 0.30, 0.35         # 上臂 / 手心 / 指尖
SH = {'R': Vector((0.19, 0, 0.43)), 'L': Vector((-0.19, 0, 0.43))}
ARM = {}
for side in ('R', 'L'):
    sh = empty(f"Girl_Shoulder_{side}", SH[side], pelvis)
    obj(f"Girl_UpperArm_{side}", 'cyl', (0, 0, -0.14), (0.075, 0.075, 0.3), M['jacket'], sh)
    el = empty(f"Girl_Elbow_{side}", (0, 0, -L1), sh)
    obj(f"Girl_Forearm_{side}", 'cyl', (0, 0, -0.13), (0.065, 0.065, 0.26), M['jacket'], el)
    obj(f"Girl_Hand_{side}", 'sphere', (0, 0, -0.30), (0.055, 0.035, 0.1), M['skin'], el)
    ARM[side] = (sh, el)
LEG = {}
for side, x in (('R', 0.09), ('L', -0.09)):
    hp = empty(f"Girl_Hip_{side}", (x, 0, -0.03), pelvis)
    obj(f"Girl_Thigh_{side}", 'cyl', (0, 0, -0.22), (0.13, 0.13, 0.46), M['jeans'], hp)
    kn = empty(f"Girl_Knee_{side}", (0, 0, -0.44), hp)
    obj(f"Girl_Shin_{side}", 'cyl', (0, 0, -0.22), (0.1, 0.1, 0.44), M['jeans'], kn)
    obj(f"Girl_Foot_{side}", 'cube', (0, 0.05, -0.47), (0.09, 0.22, 0.07), M['shoe'], kn)
    LEG[side] = (hp, kn)

# ---------------------------------------------------------------- kinematics
def fk(side, a, length=L2, pz=0.95):
    Rs = Euler((a[0], a[1], a[2]), 'XYZ').to_matrix()
    Re = Euler((a[3], 0, 0), 'XYZ').to_matrix()
    return Vector((0, 0, pz)) + SH[side] + Rs @ (Vector((0, 0, -L1)) + Re @ Vector((0, 0, -length)))

def solve(side, target, length=L2):
    target = Vector(target)
    sg = 1 if side == 'R' else -1
    def cost(a):
        c = (fk(side, a, length) - target).length_squared
        c += 0.0002 * (a[1] ** 2 + a[2] ** 2)
        if a[3] < 0: c += 10 * a[3] ** 2
        if a[3] > 2.6: c += 10 * (a[3] - 2.6) ** 2
        return c
    best = None
    for st in ((0.5, 0, 0, 1.0), (1.2, 0, 0.4 * sg, 1.5), (0.2, 0, 0, 0.3), (1.6, -0.3 * sg, 0.5 * sg, 2.2)):
        a = list(st); c = cost(a); step = 0.3
        while step > 1e-5:
            imp = False
            for i in range(4):
                for d in (step, -step):
                    b = a[:]; b[i] += d; cb = cost(b)
                    if cb < c: a, c, imp = b, cb, True
            if not imp: step *= 0.5
        if best is None or c < best[1]: best = (a, c)
    err = (fk(side, best[0], length) - target).length
    print(f"  IK {side} -> {tuple(round(v,3) for v in target)}  err={err*100:.1f}cm")
    return tuple(best[0])

# 步行
def walk_w(f): return 1.0 - ease((f - 130) / 30)
W, P, GY, BOB = {}, {}, {}, {}
p = y = 0.0
for f in range(0, END + 2):
    w = walk_w(f)
    if f > 0: p += w * 2 * math.pi / 24; y += w * SPEED
    W[f], P[f], GY[f] = w, p, y
    BOB[f] = -w * 0.035 * math.sin(p) ** 2
def G(f): return Vector((0, GY[f], 0))

HEAD_PITCH = [(1, 0), (128, 0), (145, -0.35), (178, -0.3), (192, 0.0), (END, 0)]
HEAD_YAW = [(1, 0), (268, 0), (286, 0.4), (300, 0.4), (320, -0.25), (END, -0.25)]
EAR_LOCAL = Vector((-0.108, 0.01, 0.1))
def ear_pos(f):
    r = Euler((sched(HEAD_PITCH, f), 0, sched(HEAD_YAW, f)), 'XYZ').to_matrix()
    return G(f) + Vector((0, 0, 0.95 + BOB[f] + 0.5)) + r @ EAR_LOCAL

CASE_OFF = Vector((0, 0.015, 0.035))
SLOT_L = Vector((-0.015, 0, 0.012))

print("Solving poses...")
R_POCKET = solve('R', (0.2, 0.04, 0.86))
R_HOLD = solve('R', (0.07, 0.30, 1.20))
R_LOW = solve('R', (0.17, 0.16, 0.98))
slot_rs = fk('R', R_HOLD) + CASE_OFF + SLOT_L            # root 空间
L_GRAB_PRE = solve('L', slot_rs + Vector((-0.04, 0.04, 0.07)), LT)
L_GRAB = solve('L', slot_rs, LT)
L_LIFT = solve('L', slot_rs + Vector((-0.03, 0.02, 0.12)), LT)
ear_rs = Vector((0, 0, 0.95 + 0.5)) + EAR_LOCAL
L_EAR_PRE = solve('L', ear_rs + Vector((-0.05, 0.05, -0.02)), LT)
L_EAR = solve('L', ear_rs, LT)

def swing(side, f):
    w, s = W[f], math.sin(P[f])
    sg = 1 if side == 'R' else -1
    return (sg * 0.35 * w * s, -0.08 * sg, 0.0, 0.2 + 0.15 * w)

S = 'SWING'
TRACK = {
    'R': [(1, S), (100, S), (112, R_POCKET), (118, R_POCKET), (140, R_HOLD), (242, R_HOLD), (262, R_LOW), (END, R_LOW)],
    'L': [(1, S), (158, S), (172, L_GRAB_PRE), (178, L_GRAB), (182, L_LIFT), (194, L_EAR_PRE),
          (200, L_EAR), (214, L_EAR), (236, S), (END, S)],
}
def arm(side, f):
    tr = TRACK[side]
    ev = lambda pose: swing(side, f) if pose == S else pose
    if f <= tr[0][0]: return ev(tr[0][1])
    for (f0, a0), (f1, a1) in zip(tr, tr[1:]):
        if f <= f1:
            t = ease((f - f0) / (f1 - f0)); A, B = ev(a0), ev(a1)
            return tuple(lerp(A[i], B[i], t) for i in range(4))
    return ev(tr[-1][1])

def hand_pos(side, f, length=L2):
    return G(f) + fk(side, arm(side, f), length, 0.95 + BOB[f])
def case_pos(f): return hand_pos('R', f) + CASE_OFF

# ---------------------------------------------------------------- props
def make_bud(name, parent=None):
    g = empty(name, parent=parent, size=0.02)
    obj(name + "_Body", 'sphere', (0, 0, 0), (0.024, 0.022, 0.022), M['white'], g)
    obj(name + "_Stem", 'cyl', (0, 0, -0.022), (0.009, 0.009, 0.032), M['white'], g)
    obj(name + "_LED", 'sphere', (-0.011, 0, 0.002), (0.006, 0.006, 0.006), LED_BUD, g)
    return g

case = empty("EarCase", size=0.05)
obj("EarCase_Base", 'cube', (0, 0, 0), (0.062, 0.03, 0.035), M['white'], case)
obj("EarCase_LED", 'sphere', (0, 0.0155, -0.004), (0.005, 0.003, 0.005), LED_CASE, case)
lid = empty("EarCase_LidHinge", (0, -0.015, 0.0175), case, 0.02)
obj("EarCase_Lid", 'cube', (0, 0.015, 0.007), (0.062, 0.03, 0.014), M['white'], lid)
bud_case_L = make_bud("Bud_Case_L", case); bud_case_L.location = SLOT_L
bud_case_R = make_bud("Bud_Case_R", case); bud_case_R.location = (0.015, 0, 0.012)
bud_hand = make_bud("Bud_InHand")
bud_ear = make_bud("Bud_OnEar", head); bud_ear.location = EAR_LOCAL

def vis(o, frames_on):
    """frames_on = [(f, on?)]，在 f-1/f 处阶跃"""
    for f, on in frames_on:
        o.scale = (0, 0, 0) if on else (1, 1, 1); key(o, "scale", f - 1)
        o.scale = (1, 1, 1) if on else (0, 0, 0); key(o, "scale", f)

vis(case, [(110, True)])
vis(bud_case_L, [(178, False)])
vis(bud_hand, [(178, True), (200, False)])
vis(bud_ear, [(200, True)])
for f, a in ((1, 0), (152, 0), (162, 1.95), (END, 1.95)):
    lid.rotation_euler = (a, 0, 0); key(lid, "rotation_euler", f)

def led(m, keys):
    s = m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
    for f, v in keys:
        s.default_value = v; s.keyframe_insert("default_value", frame=f)
led(LED_CASE, [(1, 0), (153, 0), (156, 12), (175, 12), (185, 0)])
led(LED_BUD, [(1, 0), (199, 0), (201, 40), (206, 30), (230, 6), (END, 6)])

# ---------------------------------------------------------------- bake girl
print("Baking girl...")
for f in range(1, END + 1):
    root.location = G(f); key(root, "location", f)
    pelvis.location = (0, 0, 0.95 + BOB[f]); key(pelvis, "location", f)
    head.rotation_euler = (sched(HEAD_PITCH, f), 0, sched(HEAD_YAW, f)); key(head, "rotation_euler", f)
    for side, ph in (('L', P[f]), ('R', P[f] + math.pi)):
        hp, kn = LEG[side]
        hp.rotation_euler = (0.38 * W[f] * math.sin(ph), 0, 0); key(hp, "rotation_euler", f)
        kn.rotation_euler = (-W[f] * (0.1 + 0.65 * max(0, math.cos(ph))), 0, 0); key(kn, "rotation_euler", f)
        sh, el = ARM[side]; a = arm(side, f)
        sh.rotation_euler = a[:3]; key(sh, "rotation_euler", f)
        el.rotation_euler = (a[3], 0, 0); key(el, "rotation_euler", f)
    if f >= 105:
        case.location = case_pos(f); key(case, "location", f)
    if 176 <= f <= 201:
        bud_hand.location = hand_pos('L', f, LT); key(bud_hand, "location", f)

# 定格时给女孩一个轮廓光
rim_d = bpy.data.lights.new("PV_Rim", 'AREA'); rim_d.size = 1.5
rim = bpy.data.objects.new("RimLight", rim_d); col.objects.link(rim); rim.parent = root
rim.location = (1.3, -1.2, 2.2)
rim.rotation_euler = (Vector((0, 0, 1.4)) - rim.location).to_track_quat('-Z', 'Y').to_euler()
for f, e in ((1, 0), (FREEZE, 0), (FREEZE + 8, 250), (END, 250)):
    rim_d.energy = e; rim_d.keyframe_insert("energy", frame=f)

# ================================================================ WORLD MOTION (会被冻结)
WF = list(range(1, FREEZE - 8, 2)) + list(range(FREEZE - 8, FREEZE + 1)) + [END]

print("Crowd...")
CROWD_COL = [(0.25, 0.25, 0.28), (0.15, 0.2, 0.3), (0.5, 0.45, 0.38), (0.3, 0.33, 0.25),
             (0.35, 0.25, 0.2), (0.6, 0.6, 0.62), (0.1, 0.1, 0.12), (0.4, 0.3, 0.35)]
lanes = [(-1.7, -0.9), (0.9, 1.6), (1.7, 2.6), (-11.2, -8.8)]
for i in range(44):
    lx = random.choice(lanes); x = random.uniform(*lx)
    d = random.choice((1, -1)); v = random.uniform(1.0, 1.6) if random.random() > 0.12 else 0.0
    y0 = random.uniform(-20, 45); h = random.uniform(0.9, 1.1)
    c = CROWD_COL[i % len(CROWD_COL)]
    pr = empty(f"Ped_{i}", (x, y0, 0), size=0.3)
    pr.scale = (h, h, h); pr.rotation_euler = (0, 0, 0 if d > 0 else math.pi)
    body = mat(f"ped{i%8}", c)
    obj(f"Ped_{i}_Torso", 'sphere', (0, 0, 1.22), (0.36, 0.24, 0.62), body, pr)
    obj(f"Ped_{i}_Head", 'sphere', (0, 0, 1.64), (0.2, 0.22, 0.24), M['skin'], pr)
    obj(f"Ped_{i}_HairTop", 'sphere', (0, -0.02, 1.68), (0.21, 0.22, 0.2), M['hair'] if i % 3 else M['pole'], pr)
    lims = []
    for s, zz, ln, mm in ((-1, 0.9, 0.9, M['jeans']), (1, 0.9, 0.9, M['jeans']),
                          (-1, 1.45, 0.62, body), (1, 1.45, 0.62, body)):
        xx = 0.09 * s if zz < 1 else 0.22 * s
        pv = empty(f"Ped_{i}_Pv{len(lims)}", (xx, 0, zz), pr, 0.05)
        obj(f"Ped_{i}_Limb{len(lims)}", 'cyl', (0, 0, -ln / 2), (0.11, 0.11, ln), mm, pv)
        lims.append(pv)
    if random.random() < 0.3:   # 有人拿着购物袋
        obj(f"Ped_{i}_Bag", 'cube', (0, 0, -0.66), (0.08, 0.3, 0.35),
            mat("bag", (0.8, 0.7, 0.5)), lims[3])
    ph0 = random.uniform(0, 6.28)
    for f in WF:
        t = teff(f); dist = v * t / FPS
        ph = ph0 + dist / 0.65 * math.pi
        pr.location = (x, y0 + d * dist, 0.02 * abs(math.sin(ph)) if v else 0)
        key(pr, "location", f)
        amp = 0.4 if v else 0.0
        for k, pv in enumerate(lims):
            sg = (1 if k in (0, 3) else -1)
            pv.rotation_euler = (sg * amp * math.sin(ph) * (1 if k < 2 else 0.8), 0, 0)
            key(pv, "rotation_euler", f)

print("Traffic...")
CAR_COL = [(0.95, 0.75, 0.05), (0.7, 0.05, 0.05), (0.9, 0.9, 0.9), (0.08, 0.2, 0.55),
           (0.03, 0.03, 0.03), (0.55, 0.56, 0.58), (0.95, 0.75, 0.05), (0.2, 0.35, 0.3)]
for i in range(10):
    d = 1 if i % 2 == 0 else -1
    lane_x = -3.6 if d > 0 else -6.6
    v = random.uniform(7, 11)
    y0 = random.uniform(-75, -5) if d > 0 else random.uniform(15, 95)
    bus = (i == 3)
    car = empty(f"Car_{i}", (lane_x, y0, -0.15), size=1)
    car.rotation_euler = (0, 0, 0 if d > 0 else math.pi)
    cm = mat(f"car{i}", CAR_COL[i % len(CAR_COL)], rough=0.3, metal=0.4)
    if bus:
        obj(f"Car_{i}_Body", 'cube', (0, 0, 1.7), (2.5, 11, 2.8), mat("bus", (0.1, 0.45, 0.25)), car)
        obj(f"Car_{i}_Win", 'cube', (0, 0, 2.2), (2.55, 10, 0.9), M['glass'], car)
        wy = 3.6
    else:
        obj(f"Car_{i}_Body", 'cube', (0, 0, 0.6), (1.8, 4.3, 0.7), cm, car)
        obj(f"Car_{i}_Cabin", 'cube', (0, -0.2, 1.15), (1.6, 2.3, 0.55), M['glass'], car)
        wy = 1.35
    for sx in (-1, 1):
        for sy in (-1, 1):
            obj(f"Car_{i}_Wheel_{sx}{sy}", 'cyl', (0.88 * sx, wy * sy, 0.33), (0.64, 0.64, 0.25), M['tire'], car,
                rot=(0, math.pi / 2, 0))
        obj(f"Car_{i}_Light_{sx}", 'cube', (0.6 * sx, (5.5 if bus else 2.15), 0.7), (0.3, 0.05, 0.12), M['headl'], car)
    for f in WF:
        car.location = (lane_x, y0 + d * v * teff(f) / FPS, -0.15); key(car, "location", f)

print("Pigeons & leaves...")
for i in range(12):
    p0 = Vector((random.uniform(0.6, 2.8), random.uniform(8.8, 12.5), 0.0))
    ang = random.uniform(0, 2 * math.pi)
    dirv = Vector((math.cos(ang), math.sin(ang), 0))
    tf = random.uniform(150, 172)
    pg = empty(f"Pigeon_{i}", p0, size=0.1)
    pg.rotation_euler = (0, 0, ang - math.pi / 2)
    obj(f"Pigeon_{i}_Body", 'sphere', (0, 0, 0.1), (0.12, 0.26, 0.13), M['pigeon'], pg)
    obj(f"Pigeon_{i}_Head", 'sphere', (0, 0.13, 0.19), (0.07, 0.08, 0.08), M['pigeon'], pg)
    wings = []
    for s in (-1, 1):
        wp = empty(f"Pigeon_{i}_WingPv{s}", (0.05 * s, 0, 0.14), pg, 0.03)
        obj(f"Pigeon_{i}_Wing{s}", 'cube', (0.15 * s, 0, 0), (0.3, 0.14, 0.01), M['pigeon'], wp)
        wings.append((s, wp))
    for f in WF:
        t = teff(f)
        if t > tf:
            dt = (t - tf) / FPS
            pg.location = p0 + dirv * (2.0 * dt) + Vector((0, 0, 1.25 * dt + 0.15 * dt * dt))
            fl = 0.9 * math.sin(t * 1.3 + i)
        else:
            pg.location = p0; fl = -0.1
        key(pg, "location", f)
        for s, wp in wings:
            wp.rotation_euler = (0, -s * fl, 0); key(wp, "rotation_euler", f)

LEAF_COL = [(0.85, 0.45, 0.08), (0.9, 0.7, 0.1), (0.6, 0.25, 0.05), (0.95, 0.95, 0.92)]
for i in range(30):
    zf = random.uniform(0.5, 3.4); x0 = random.uniform(-1.6, 2.6); yb = random.uniform(5, 12)
    fallv = random.uniform(0.3, 0.5); sp = random.uniform(1.5, 4)
    lf = obj(f"Leaf_{i}", 'cube', (0, 0, 0), (0.07, 0.05, 0.004) if i % 5 else (0.12, 0.09, 0.003),
             mat(f"leaf{i%4}", LEAF_COL[i % 4], rough=0.8))
    for f in WF:
        t = teff(f) / FPS; tfz = teff(FREEZE) / FPS
        lf.location = (x0 + 0.25 * math.sin(t * 1.3 + i), yb + 0.2 * math.cos(t + i), zf + fallv * (tfz - t))
        lf.rotation_euler = (t * sp, t * sp * 0.7 + i, t * 0.5)
        key(lf, "location", f); key(lf, "rotation_euler", f)

# ================================================================ CAMERAS
print("Cameras...")
def hn(f, amp):
    return Vector((math.sin(f * 0.13) + 0.5 * math.sin(f * 0.31 + 1),
                   math.sin(f * 0.11 + 2) + 0.5 * math.sin(f * 0.27),
                   0.7 * math.sin(f * 0.17 + 4))) * amp

def make_cam(name, lens, fstop=None):
    cd = bpy.data.cameras.new(name); cd.lens = lens; cd.clip_start = 0.01; cd.clip_end = 400
    if fstop:
        cd.dof.use_dof = True; cd.dof.aperture_fstop = fstop
    o = bpy.data.objects.new(name, cd); col.objects.link(o)
    return o

def bake_cam(cam, f0, f1, fn):
    prev = None
    for f in range(max(1, f0 - 1), min(END, f1 + 1) + 1):
        pos, tgt = fn(f)
        dv = tgt - pos
        q = dv.to_track_quat('-Z', 'Y')
        e = q.to_euler('XYZ', prev) if prev else q.to_euler('XYZ'); prev = e
        cam.location = pos; cam.rotation_euler = e
        key(cam, "location", f); key(cam, "rotation_euler", f)
        if cam.data.dof.use_dof:
            cam.data.dof.focus_distance = dv.length
            cam.data.dof.keyframe_insert("focus_distance", frame=f)

SHOTS = []
# S1 跟随全景（开场吊臂下降）
c1 = make_cam("CAM_S1_Follow_Wide", 30)
bake_cam(c1, 1, 90, lambda f: (G(f) + Vector((1.3, -3.6, 1.7 + 2.2 * (1 - ease(f / 45)))) + hn(f, 0.02),
                               G(f) + Vector((0, 0.8, 1.25))))
SHOTS.append((1, "S1 跟随-街道全景", c1))
# S2 侧前方中景：掏口袋、拿出耳机仓
c2 = make_cam("CAM_S2_Pocket_Medium", 45)
bake_cam(c2, 91, 150, lambda f: (G(f) + Vector((1.35, 1.1, 1.2)) + hn(f, 0.012),
                                 G(f) + Vector((0.12, 0.05, 0.98 + 0.25 * ease((f - 115) / 25)))))
SHOTS.append((91, "S2 中景-掏出耳机仓", c2))
# S3 耳机仓特写：开盖、拿耳机
c3 = make_cam("CAM_S3_Case_CU", 50, 2.8)
def s3(f):
    t = case_pos(f) + Vector((-0.005, 0, 0.012))
    return t + Vector((0.09, 0.30, 0.08)) * (1.2 - 0.35 * ease((f - 151) / 28)) + hn(f, 0.002), t
bake_cam(c3, 151, 179, s3)
SHOTS.append((151, "S3 特写-耳机仓开盖", c3))
# S4 跟踪耳机 -> 耳朵特写，时间静止
def s4_target(f):
    if f < 178: return case_pos(f) + SLOT_L
    if f < 200: return hand_pos('L', f, LT)
    return ear_pos(f)
def s4(f):
    tsm = sum((s4_target(k) for k in range(f - 4, f + 1)), Vector()) / 5
    s = 1.0 - 0.5 * ease((f - 204) / 36)
    return tsm + Vector((-0.40, 0.24, 0.03)) * s + hn(f, 0.002), tsm
c4 = make_cam("CAM_S4_Earbud_Track_ECU", 55, 2.0)
bake_cam(c4, 180, 240, s4)
SHOTS.append((180, "S4 跟踪特写-戴上耳机", c4))
# S5 子弹时间环绕，拉远展示静止的世界
c5 = make_cam("CAM_S5_Freeze_Orbit", 32, 4.0)
def s5(f):
    u = ease((f - 241) / 95)
    th = math.radians(165 - 115 * u); r = 0.45 + 3.0 * u
    C = G(f) + Vector((0, 0, 1.52 - 0.25 * u))
    return C + Vector((r * math.cos(th), r * math.sin(th), 0.02 + 0.45 * u)), C
bake_cam(c5, 241, END, s5)
SHOTS.append((241, "S5 子弹时间-世界静止", c5))

scn.timeline_markers.clear()
for f, name, cam in SHOTS:
    m = scn.timeline_markers.new(name, frame=f); m.camera = cam
scn.timeline_markers.new("★ 戴上耳机 click", frame=200)
scn.timeline_markers.new("★ TIME STOP 世界静止", frame=FREEZE)
scn.camera = c1

# ================================================================ AUDIO
def make_audio(path):
    import numpy as np, wave
    sr = 44100; n = int(sr * END / FPS) + sr
    rng = np.random.default_rng(3); t = np.arange(n) / sr
    wn = rng.standard_normal(n)
    lp = lambda x, k: np.convolve(x, np.ones(k) / k, mode='same')
    amb = lp(wn, 150) * 6 + wn * 0.02
    amb += (lp(wn, 6) - lp(wn, 40)) * (0.6 + 0.4 * np.sin(2 * np.pi * 4.7 * t) * np.sin(2 * np.pi * 0.6 * t)) * 1.2
    for tc in (1.0, 3.3, 5.6, 7.4):
        amb += lp(wn, 70) * 9 * np.exp(-((t - tc) / 0.7) ** 2)
    for th, fr in ((2.2, 420), (4.9, 370), (6.8, 455)):
        env = lp(((t > th) & (t < th + 0.35)).astype(float), 400)
        amb += 0.2 * env * (0.5 * np.sign(np.sin(2 * np.pi * fr * t)) + 0.5 * np.sin(2 * np.pi * fr * 1.26 * t))
    amb /= np.max(np.abs(amb)) * 1.3
    tf = (FREEZE - 1) / FPS
    out = amb * np.clip((tf + 0.04 - t) / 0.04, 0, 1)
    tc = (200 - 1) / FPS
    out += 0.3 * (t >= tc) * np.exp(-np.maximum(t - tc, 0) * 60) * np.sin(2 * np.pi * 1700 * t)
    fade = np.clip((t - tf) / 2.5, 0, 1)
    out += fade * 0.03 * (np.sin(2 * np.pi * 220 * t) + 0.6 * np.sin(2 * np.pi * 329.6 * t) + 0.3 * np.sin(2 * np.pi * 440 * t))
    pcm = (np.clip(out, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr); wf.writeframes(pcm.tobytes())

try:
    wav = os.path.join(OUT_DIR, "previz_audio.wav")
    make_audio(wav)
    se = scn.sequence_editor_create()
    strips = se.strips if hasattr(se, "strips") else se.sequences
    strips.new_sound("StreetAmbience", wav, channel=1, frame_start=1)
    try: scn.sync_mode = 'AUDIO_SYNC'
    except Exception: pass
    print("Audio:", wav)
except Exception as ex:
    print("Audio skipped:", ex)

# ================================================================ finish
prefs.keyframe_new_interpolation_type = old_interp
scn.frame_set(1)
if bpy.context.screen:
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            sp = area.spaces.active
            sp.shading.type = 'MATERIAL'
            try:
                sp.shading.use_scene_lights = True; sp.shading.use_scene_world = True
            except Exception: pass
            sp.region_3d.view_perspective = 'CAMERA'
print("Previz done: scene", SCN_NAME, "frames 1-%d" % END)
