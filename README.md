# XingViz 星视

用一句话改你的 Blender previz。

XingViz 是一个 Blender 扩展：在 3D 视图侧边栏里输入需求，比如「S4 的机位换到右边」「时间静止提前到 190 帧」「鸽子多一倍」，它会调用 [Claude Code](https://claude.com/claude-code) 修改生成 previz 的 Python 脚本，然后自动重建场景。

*Direct your previz in plain language. XingViz sends your request to the Claude Code CLI, which edits the Python script that builds your previz scene. The add-on then re-runs the script inside Blender.*

## 功能

- **自然语言修改**：用侧边栏面板或 `Ctrl + Shift + X` 弹出对话框输入需求
- **理解上下文**：自动附带当前帧、当前镜头、时间轴标记和选中物体；可选附带视口截图，所以能直接说「这个镜头」「这个人」
- **记住对话**：连续多次修改会延续同一段对话，Claude 记得之前改过什么
- **版本历史**：每次修改前后都存档，一键撤销或恢复到任意版本
- **自动修复**：脚本报错时，把错误信息发回给 Claude 自动修复，次数可配置
- **不卡界面**：Claude 在后台线程工作，这期间 Blender 可以照常操作

## 要求

- Blender 4.2 或更高版本（在 5.1 上开发测试）
- 已安装 [Claude Code](https://docs.claude.com/claude-code) CLI 并登录：在终端运行一次 `claude`，输入 `/login`

## 安装

最简单：到 [Releases](https://github.com/imokya/xingviz/releases) 下载 `xingviz-<版本>.zip`，然后跳到第 2 步。

1. 或者自己打包（先克隆仓库）：
   ```bash
   git clone https://github.com/imokya/xingviz.git && cd xingviz
   ```
   然后在仓库根目录运行：
   ```bash
   ./scripts/build.sh
   ```
   会生成 `dist/xingviz-<版本>.zip`。
2. Blender → 编辑 → 偏好设置 → 获取扩展 → 右上角 ⌄ → **从磁盘安装…**，选择这个 zip。

开发时可以把 `xingviz/` 目录软链到 Blender 的扩展目录，改完代码后重启 Blender 即可生效：
```bash
ln -s "$PWD/xingviz" ~/Library/Application\ Support/Blender/<版本>/extensions/user_default/xingviz
```

## 使用

1. 3D 视图按 `N` 打开侧边栏，找到 **XingViz** 标签页。
2. 选择一个 previz 脚本，或点 **+** 从模板新建。`examples/earbuds_previz.py` 是一个完整示例：女孩在街上戴上耳机，世界瞬间静止。
3. 输入需求，点 **发送**。

## 工作原理

```
需求 + 上下文 ──► claude -p（只允许 Read/Edit/Write/Glob/Grep，工作目录是脚本所在文件夹）
                      │ 修改脚本
                      ▼
             保存新版本（.xingviz/<脚本名>/vNNN.py）
                      ▼
             在 Blender 中 exec 脚本重建场景 ──报错──► 把错误发回 Claude 修复
```

**脚本是唯一的"源文件"**：场景永远由脚本生成，所以每个版本都能完整复现、随时回退。版本和对话状态保存在脚本旁边的 `.xingviz/` 目录中。

### 偏好设置

| 选项 | 说明 |
|---|---|
| Claude CLI 路径 | 留空则自动查找 |
| 模型 | 传给 `claude --model`，例如 `opus`、`sonnet` |
| 自动修复 / 最多次数 | 脚本报错时自动发回给 Claude 修复 |
| 修改后先确认再运行 | 先看改动，再手动点「运行修改」 |
| 额外风格要求 | 每次请求都会附加的全局要求 |

## 安全说明

Claude 生成的脚本会在你的 Blender 里直接执行，拥有和普通 Python 脚本一样的权限。Claude 本身只被允许读写脚本所在的文件夹，且不能执行命令。如果需要先检查代码，请打开「修改后先确认再运行」。

## 项目结构

```
xingviz/                  扩展源码（打包进 zip 的部分）
  blender_manifest.toml
  __init__.py             注册
  core.py                 Claude 进程、版本管理、脚本执行
  operators.py            操作（发送、撤销、恢复……）
  panel.py                侧边栏界面
  preferences.py          偏好设置
  properties.py           场景/运行时属性
  templates/blank_previz.py
examples/                 示例 previz 脚本
scripts/build.sh          打包
```

## 许可证

GPL-3.0-or-later，详见 [LICENSE](LICENSE)。
