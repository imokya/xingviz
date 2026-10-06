#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""XingViz 桥接客户端：从命令行操控开启了桥接模式的 Blender。

  xvctl.py ping
  xvctl.py scene
  xvctl.py exec -c "print(bpy.context.scene.name)"     # 设置 _result 可返回值
  xvctl.py exec -f script.py
  xvctl.py exec <<'PY'                                  # 从标准输入读多行代码
  ...
  PY
  xvctl.py shot [-o out.png] [--frame 120] [--mode camera|area] [--width 960]
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

HOME_DIR = os.environ.get("XINGVIZ_HOME") or os.path.expanduser("~/.xingviz")
INFO_FILE = os.path.join(HOME_DIR, "bridge.json")


def _alive(pid):
    if os.name == "nt":
        # Windows 上 os.kill(pid, 0) 会发送 CTRL_C_EVENT，不能用来探测进程
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def call(route, payload=None, timeout=180):
    try:
        with open(INFO_FILE, encoding="utf-8") as fh:
            info = json.load(fh)
    except OSError:
        sys.exit("桥接未开启：在 Blender 的 XingViz 面板里点「开启桥接」")
    try:
        alive = _alive(int(info.get("pid", 0)))
    except ValueError:
        alive = False
    if not alive:
        sys.exit("Blender 已经关闭（桥接信息是上次留下的）：请打开 Blender 并开启桥接")
    req = urllib.request.Request(
        f"http://127.0.0.1:{info['port']}/{route}",
        data=json.dumps(payload or {}).encode("utf-8"),
        headers={"X-XingViz-Token": info["token"], "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as ex:
        return json.load(ex)
    except urllib.error.URLError as ex:
        sys.exit(f"连不上 Blender（{ex.reason}）：Blender 是否还开着、桥接是否开启？")
    except (OSError, ValueError) as ex:  # 连接被重置、桥接中途关闭等
        sys.exit(f"与 Blender 的连接中断（{ex}）")


def main():
    ap = argparse.ArgumentParser(description="XingViz bridge client")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("ping")
    sp.add_parser("scene")
    e = sp.add_parser("exec")
    g = e.add_mutually_exclusive_group()
    g.add_argument("-c", "--code")
    g.add_argument("-f", "--file")
    s = sp.add_parser("shot")
    s.add_argument("-o", "--out", default="")
    s.add_argument("--frame", type=int)
    s.add_argument("--mode", choices=("camera", "area"), default="camera")
    s.add_argument("--width", type=int, default=960)
    a = ap.parse_args()

    if a.cmd == "exec":
        if a.code is not None:
            code = a.code
        elif a.file:
            code = open(a.file, encoding="utf-8").read()
        else:
            code = sys.stdin.read()
        res = call("exec", {"code": code})
    elif a.cmd == "shot":
        p = {"mode": a.mode, "width": a.width, "path": os.path.abspath(a.out) if a.out else ""}
        if a.frame is not None:
            p["frame"] = a.frame
        res = call("screenshot", p)
    else:
        res = call(a.cmd)

    if a.cmd == "scene" and res.get("ok"):
        print(res["context"])
    else:
        out = res.pop("stdout", "")
        if out:
            print(out, end="" if out.endswith("\n") else "\n")
        err = res.pop("error", "")
        if res:
            print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
        if err:
            print(err, file=sys.stderr)
    sys.exit(0 if res.get("ok", True) else 1)


if __name__ == "__main__":
    main()
