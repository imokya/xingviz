# XingViz 星视

用一句话改你的 Blender previz。

在 3D 视图里点 XingViz 按钮，输入「镜头跟随女孩，推近到耳朵特写」这样的需求，[Claude Code](https://claude.com/claude-code) 会直接修改当前场景，改完自己渲染关键帧检查。

*Describe a change in plain language; Claude Code edits your open Blender scene and checks its own work.*

## 准备

1. **Blender 4.2 或更高**（macOS / Windows / Linux）
2. **Claude Code**：按[官方说明](https://docs.claude.com/claude-code)安装，然后在终端运行一次 `claude`，输入 `/login` 登录

## 安装

1. 到 [Releases](https://github.com/imokya/xingviz/releases) 下载最新的 `xingviz-x.y.z.zip`
2. Blender → 编辑 → 偏好设置 → 获取扩展 → 右上角 ⌄ → **从磁盘安装…** → 选这个 zip

## 使用

1. 点 3D 视图底部中间的 **XingViz** 按钮（或按 `Ctrl + Shift + X`）
2. 输入需求，点 **发送**
3. 等按钮显示「完成」，点开看 Claude 的说明

不满意可以接着说，或者点 **撤销**（`Cmd/Ctrl + Z` 也行）。点 **新对话** 让 Claude 忘掉之前的上下文。

小技巧：

- 先选中物体、把时间轴拖到那一帧，再说「这个人」「这个镜头」，Claude 能看懂
- 打开 **截图**，会把当前视口画面一起发过去
- 小改动打开 **快速**，响应更快

## 设置

偏好设置 → 扩展 → XingViz 展开：

| 选项 | 说明 |
|---|---|
| Claude CLI 路径 | 一般留空，自动查找；显示「未找到」时手动选 `claude` 可执行文件 |
| 模型 | 例如 `opus`、`sonnet`，留空用 Claude Code 默认 |
| 快速模式模型 | 打开「快速」时用的模型 |
| 超时 | 单次请求最长时间 |
| 额外风格要求 | 每次都附加给 Claude，例如「物体名用英文」 |
| 悬浮按钮 | 关掉后用快捷键或侧边栏（N 面板 → XingViz） |
| 桥接端口 / 自动开启 | 见下方「桥接」 |

数据存放在 `~/.xingviz`，可用环境变量 `XINGVIZ_HOME` 改到别处。

## 常见问题

- **未找到 claude**：确认终端里能运行 `claude`，然后在设置里手动指定路径。Windows 上一般是 `%USERPROFILE%\.local\bin\claude.exe` 或 `%APPDATA%\npm\claude.cmd`
- **提示没登录**：终端运行 `claude`，输入 `/login`
- **日志**：点面板里的 **日志**，或在文本编辑器里打开 `XingViz Log`

## 桥接（进阶）

点 **桥接** 后，本机其它 Claude Code 会话（比如桌面版对话）也能操控这个 Blender：

```bash
python3 ~/.xingviz/xvctl.py ping
python3 ~/.xingviz/xvctl.py exec -c "_result = [o.name for o in bpy.context.selected_objects]"
python3 ~/.xingviz/xvctl.py shot --frame 120 -o shot.png
```

桥接只监听 127.0.0.1，每个请求都要带随机令牌。插件自己发送需求时会临时开启，结束后自动关闭。

## 从源码打包

```bash
git clone https://github.com/imokya/xingviz.git && cd xingviz
BLENDER=/path/to/blender ./scripts/build.sh
```

生成 `dist/xingviz-<版本>.zip`。macOS 上不设置 `BLENDER` 会默认用 `/Applications/Blender.app`。

## 许可

GPL-3.0-or-later
