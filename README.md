# XingViz 星视

用一句话改你的 Blender previz。

在 3D 视图里点 XingViz 按钮，输入「镜头跟随女孩，推近到耳朵特写」这样的需求，AI 会直接修改当前场景，改完自己渲染关键帧检查。支持 **Claude Code** 和 **Codex（ChatGPT）**。

*Describe a change in plain language; Claude Code or Codex edits your open Blender scene and checks its own work.*

## 1. 安装 AI 工具（二选一）

| | Claude Code | Codex（ChatGPT） |
|---|---|---|
| 安装 | [安装说明](https://docs.claude.com/claude-code) | [安装说明](https://developers.openai.com/codex/cli) |
| 用账号登录 | 终端运行 `claude`，输入 `/login` | 终端运行 `codex login` |
| 用 API Key | 不用登录，第 3 步填 Key | 不用登录，第 3 步填 Key |

- 有 Claude 或 ChatGPT 订阅：用账号登录
- 按量付费，或者用代理/中转服务：用 API Key

## 2. 安装插件

1. 到 [Releases](https://github.com/imokya/xingviz/releases) 下载最新的 `xingviz-x.y.z.zip`
2. Blender → 编辑 → 偏好设置 → 获取扩展 → 右上角 ⌄ → **从磁盘安装…** → 选这个 zip

需要 Blender 4.2 或更高，macOS / Windows / Linux 都可以。

## 3. 设置

偏好设置 → 扩展 → XingViz 展开：

1. **AI**：选 Claude Code 或 Codex
2. **登录方式**：
   - **本机登录**：用第 1 步登录的账号，不用填别的
   - **API Key**：填入 Key；用代理就在 **API 地址** 填代理地址，否则留空
3. 下面显示「已找到 …」就可以用了

API Key 以明文保存在本机的 Blender 偏好设置里，不会上传到别处。

## 4. 使用

1. 点 3D 视图底部中间的 **XingViz** 按钮（或按 `Ctrl + Shift + X`）
2. 输入需求，点 **发送**
3. 等按钮显示「完成」，点开看 AI 的说明

不满意可以接着说，或者点 **撤销**（`Cmd/Ctrl + Z` 也行）。**新对话** 会让 AI 忘掉之前的上下文。输入框左边可以随时切换 AI。

小技巧：

- 先选中物体、把时间轴拖到那一帧，再说「这个人」「这个镜头」，AI 能看懂
- 打开 **截图**，会把当前视口画面一起发过去
- 小改动打开 **快速**，响应更快

## 常见问题

- **显示「未找到」**：确认终端里能运行 `claude` 或 `codex`，再在设置的 **程序路径** 里手动选择。Windows 上一般在 `%USERPROFILE%\.local\bin\` 或 `%APPDATA%\npm\`
- **提示没登录 / 401**：本机登录的话，重新执行第 1 步的登录命令；API Key 的话，检查 Key 和 API 地址
- **Codex 提示模型需要更新版本**：终端运行 `codex update`
- **查看详细过程**：点面板里的 **日志**

## 其它设置

| 选项 | 说明 |
|---|---|
| 模型 | 留空用默认模型；Claude 可填 `opus`、`sonnet` |
| 超时 | 单次请求最长时间 |
| 额外要求 | 每次都附加给 AI，例如「物体名用英文」 |
| 悬浮按钮 | 关掉后用快捷键或侧边栏（N 面板 → XingViz） |
| 桥接端口 / 自动开启 | 见下方「桥接」 |

数据存放在 `~/.xingviz`，可用环境变量 `XINGVIZ_HOME` 改到别处。

## 桥接（进阶）

点 **桥接** 后，本机其它 AI 工具（比如 Claude 桌面版、Codex 对话）也能操控这个 Blender：

```bash
python3 ~/.xingviz/xvctl.py ping
python3 ~/.xingviz/xvctl.py exec -c "_result = [o.name for o in bpy.context.selected_objects]"
python3 ~/.xingviz/xvctl.py shot --frame 120 -o shot.png
```

桥接只监听 127.0.0.1，每个请求都要带随机令牌。插件自己发送需求时会临时开启，结束后自动关闭。

想接入别的 AI 命令行工具，参考 [`xingviz/agents.py`](xingviz/agents.py)，加一个类即可。

## 从源码打包

```bash
git clone https://github.com/imokya/xingviz.git && cd xingviz
BLENDER=/path/to/blender ./scripts/build.sh
```

生成 `dist/xingviz-<版本>.zip`。macOS 上不设置 `BLENDER` 会默认用 `/Applications/Blender.app`。

## 许可

GPL-3.0-or-later
