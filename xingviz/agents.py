# SPDX-License-Identifier: GPL-3.0-or-later
"""支持的 AI 智能体（命令行工具）。

每个智能体负责三件事：
  find()     找到命令行程序
  command()  拼出一次请求的命令行和标准输入
  Parser     把它的 JSON 输出翻译成统一事件：
             ("session", id) / ("activity", 文字) / ("result", {"text", "is_error"}) / ("error", 文字)

要接入新的智能体，照着 Claude / Codex 写一个类，加进 AGENTS 即可。
"""
import os
import shutil

from .preferences import expand


def _find(custom, candidates, names):
    if custom:
        p = expand(custom)
        return p if os.path.isfile(p) else ""
    for c in candidates:
        p = expand(c)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return ""


def _npm_shim(path, package, script):
    """Windows 上 npm 装的是 .cmd，经 cmd.exe 转发时多行参数会被截断，改为直接用 node 运行"""
    if os.name == "nt" and path.lower().endswith((".cmd", ".bat")):
        js = os.path.join(os.path.dirname(path), "node_modules", *package.split("/"), *script.split("/"))
        node = shutil.which("node") or os.path.join(os.path.dirname(path), "node.exe")
        if os.path.isfile(js) and os.path.isfile(node):
            return [node, js]
    return [path]


def _first_line(text):
    lines = (text or "").strip().splitlines()
    return lines[0] if lines else ""


def _describe_command(cmd):
    for key, text in ((" exec", "在 Blender 中执行代码"), (" shot", "渲染画面检查"), (" scene", "查看场景")):
        if key in cmd and "xvctl" in cmd:
            return text
    return "运行命令"


# ------------------------------------------------------------------ Claude Code

class Claude:
    key = "claude"
    label = "Claude Code"
    install_hint = "安装 Claude Code：https://docs.claude.com/claude-code"
    login_hint = "在终端运行 claude，输入 /login"
    key_hint = "Anthropic API Key（sk-ant-…）"
    view_hint = "用 Read 工具"

    if os.name == "nt":
        candidates = ("~/.local/bin/claude.exe", "%APPDATA%/npm/claude.cmd")
    else:
        candidates = ("~/.local/bin/claude", "~/.claude/local/claude", "/opt/homebrew/bin/claude",
                      "/usr/local/bin/claude", "~/.npm-global/bin/claude", "~/.volta/bin/claude")

    @classmethod
    def find(cls, prefs):
        return _find(prefs.claude_path, cls.candidates, ("claude",))

    @staticmethod
    def env(prefs, env):
        if prefs.auth == 'API':
            if prefs.claude_api_key:
                env["ANTHROPIC_API_KEY"] = prefs.claude_api_key
            if prefs.claude_api_base:
                env["ANTHROPIC_BASE_URL"] = prefs.claude_api_base

    @staticmethod
    def command(exe, prefs, *, cli, system, message, session, image):
        cmd = _npm_shim(exe, "@anthropic-ai/claude-code", "cli.js") + [
            "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
            "--permission-mode", "acceptEdits",
            "--allowedTools", f"Bash({cli}:*)", "Read", "Write", "Edit", "Glob", "Grep",
            "--append-system-prompt", system]
        if session:
            cmd += ["--resume", session]
        if prefs.fast_mode:
            cmd += ["--model", prefs.fast_model or "sonnet", "--effort", "low"]
        elif prefs.model:
            cmd += ["--model", prefs.model]
        if image:
            message += f"\n- 用户附带了当前 3D 视口截图：{image}（请用 Read 查看）"
        return cmd, message

    class Parser:
        def feed(self, d):
            t = d.get("type")
            if t == "system" and d.get("subtype") == "init" and d.get("session_id"):
                return [("session", d["session_id"])]
            if t == "stream_event":
                ev = d.get("event") or {}
                if ev.get("type") == "content_block_start":
                    kind = (ev.get("content_block") or {}).get("type")
                    text = {"thinking": "思考中…", "tool_use": "正在编写要执行的代码…",
                            "text": "正在整理回复…"}.get(kind)
                    if text:
                        return [("activity", text)]
            elif t == "assistant":
                out = []
                for c in d.get("message", {}).get("content", []):
                    if c.get("type") == "tool_use":
                        out.append(("activity", self._tool(c)))
                    elif c.get("type") == "text" and c.get("text", "").strip():
                        out.append(("activity", _first_line(c["text"])))
                return out
            elif t == "result":
                out = [("result", {"text": d.get("result") or "", "is_error": bool(d.get("is_error"))})]
                if d.get("session_id"):
                    out.insert(0, ("session", d["session_id"]))
                return out
            return []

        @staticmethod
        def _tool(c):
            name, inp = c.get("name", ""), c.get("input") or {}
            if name == "Bash":
                return inp.get("description") or _describe_command(inp.get("command", ""))
            if name == "Read":
                return "查看 " + os.path.basename(inp.get("file_path", ""))
            return name


# ------------------------------------------------------------------ Codex（ChatGPT）

class Codex:
    key = "codex"
    label = "Codex（ChatGPT）"
    install_hint = "安装 Codex：https://developers.openai.com/codex/cli"
    login_hint = "在终端运行 codex login，用 ChatGPT 账号登录"
    key_hint = "OpenAI API Key（sk-…）"
    view_hint = "用 view_image 工具"

    if os.name == "nt":
        candidates = ("~/.local/bin/codex.exe", "%APPDATA%/npm/codex.cmd")
    else:
        candidates = ("~/.local/bin/codex", "/opt/homebrew/bin/codex", "/usr/local/bin/codex",
                      "~/.npm-global/bin/codex", "~/.volta/bin/codex")

    @classmethod
    def find(cls, prefs):
        return _find(prefs.codex_path, cls.candidates, ("codex",))

    @staticmethod
    def env(prefs, env):
        if prefs.auth == 'API' and prefs.codex_api_key:
            env["CODEX_API_KEY"] = env["OPENAI_API_KEY"] = prefs.codex_api_key

    @staticmethod
    def command(exe, prefs, *, cli, system, message, session, image):
        cmd = _npm_shim(exe, "@openai/codex", "bin/codex.js") + ["exec"]
        if session:
            cmd += ["resume"]
        # 桥接走 127.0.0.1，所以沙箱要放开网络；写入限制在工作目录
        cmd += ["--json", "--skip-git-repo-check",
                "-c", 'sandbox_mode="workspace-write"',
                "-c", "sandbox_workspace_write.network_access=true",
                "-c", 'approval_policy="never"']
        if prefs.auth == 'API' and prefs.codex_api_base:
            cmd += ["-c", f"openai_base_url={_toml_str(prefs.codex_api_base)}"]
        if prefs.fast_mode:
            cmd += ["-c", 'model_reasoning_effort="low"']
        if prefs.codex_model:
            cmd += ["-m", prefs.codex_model]
        if image:
            cmd += ["-i", image]
            message += "\n- 用户附带了当前 3D 视口截图（已作为图片附上）"
        if session:
            cmd += [session, "-"]
        else:
            cmd += ["-"]
            # Codex 没有追加系统提示词的参数，第一轮把说明放在消息前面，之后的轮次会记得
            message = f"<instructions>\n{system}\n</instructions>\n\n{message}"
        return cmd, message

    class Parser:
        def __init__(self):
            self.reply = ""
            self.error = ""

        def feed(self, d):
            t = d.get("type")
            item = d.get("item") or {}
            kind = item.get("type")
            if t == "thread.started" and d.get("thread_id"):
                return [("session", d["thread_id"])]
            if t == "item.started":
                if kind == "command_execution":
                    return [("activity", _describe_command(item.get("command", "")))]
                if kind == "reasoning":
                    return [("activity", "思考中…")]
            elif t == "item.completed":
                if kind == "agent_message" and item.get("text", "").strip():
                    self.reply = item["text"].strip()
                    return [("activity", _first_line(self.reply))]
            elif t == "error":
                self.error = _unwrap(d.get("message", ""))
            elif t == "turn.completed":
                return [("result", {"text": self.reply, "is_error": False})]
            elif t == "turn.failed":
                msg = _unwrap((d.get("error") or {}).get("message", "")) or self.error
                return [("result", {"text": msg or "Codex 运行失败", "is_error": True})]
            return []


def _unwrap(msg):
    """Codex 的错误信息常常是一段 JSON，取出里面真正的说明"""
    import json
    try:
        d = json.loads(msg)
        return (d.get("error") or {}).get("message") or d.get("message") or msg
    except (ValueError, AttributeError):
        return msg


def _toml_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


AGENTS = {a.key: a for a in (Claude, Codex)}


def current(prefs):
    return AGENTS.get(prefs.agent.lower(), Claude)
