# 终端环境核对 / Terminal environment checks

核对日期 / Checked: 2026-11-07.

MODU 是独立的 Python/Textual TUI。要保留开发进度，应给它另一个可交互终端窗格或窗口；已经运行代理的同一前台终端不能同时运行两个占满屏幕的应用。可见日志和原工具通知由宿主提供，MODU 不监听代理状态。

MODU is an independent Python/Textual TUI. Give it a separate interactive terminal pane/window so development progress stays visible. Two full-screen foreground applications cannot share the same pane. The host provides visible logs and its own notifications; MODU does not monitor agents.

| 环境 / Environment | 已确认 / Confirmed | 本项目验收 / MODU acceptance |
| --- | --- | --- |
| 通用 macOS PTY + tmux / macOS PTY + tmux | 真实命令、分屏、鼠标、真彩色 / Actual command, split panes, mouse, truecolor | 已测中英文全文、主题、缩放、搜索、书签和续读 / Tested full Chinese/English text, themes, resizing, search, bookmarks and resume |
| xterm.js 6.0.0 DOM | 独立终端渲染器 / Isolated terminal renderer | 原始 PTY 回放与图像检查通过；不等于验收使用它的每一个宿主 / Raw PTY replay and image checks passed; not a test of every host that uses it |
| Codex 旁侧终端 / Terminal beside Codex | 使用者实际工作场景 / User's actual workflow | 使用者确认右侧轨道与隐藏；自动化未控制宿主窗口 / User confirmed rail alignment/hiding; host UI not automated |
| VS Code | 官方确认终端分屏 / Officially documented split terminals | 适合该工作方式，专属原生界面未验收 / Suitable workflow; native UI not separately tested |
| Claude Code CLI | 官方确认终端运行 / Officially documented terminal CLI | 可在另一个窗格并排；没有启动真实代理任务 / Adjacent pane is suitable; no live agent task tested |
| Antigravity | 官方说明侧栏终端 / Official docs describe a side-panel terminal | 可尝试、未实测；没有列为已验证支持 / Possible, untested; not listed as verified support |

官方能力依据 / Official capability references: [VS Code split terminals](https://code.visualstudio.com/docs/terminal/basics#_groups-split-panes), [Claude Code overview](https://code.claude.com/docs/en/overview), [Antigravity integrated terminal](https://antigravity.google/docs/features#integrated-terminal).

建议为阅读窗格预留至少 42 列；小于 70 列时目录改为弹窗。终端需支持真彩色、鼠标协议和交互式全屏应用。上表中的“适合”是根据终端能力判断的工作方式，不是第三方认证或官方集成。Windows/Linux 原生终端体验尚待验收。

Allow at least 42 columns for a reading pane; contents become a modal below 70 columns. Use a terminal with truecolor, mouse reporting and interactive full-screen support. “Suitable” describes a workflow inferred from terminal capabilities, not a third-party certification or integration. Native Windows/Linux terminal acceptance remains pending.
