# 贡献 / Contributing

[中文 README](README.md) · [English README](README.en.md)

使用 Python 3.11+ 与 uv。运行 `uv sync --frozen`，然后运行 README 中的测试、静态检查和发布检查。依赖更新必须同步更新 `uv.lock` 并重新执行漏洞和许可检查。

提交缺陷时请说明系统、终端、Python 版本、窗口列数/行数、重现步骤。请使用原创、合成或明确允许再分发的最小文字。不要上传书库、商业书籍、聊天记录、终端原始转储、环境变量、密钥或包含个人路径的截图。真实终端测试产生的诊断文件只应保留在本机。

改动应保持纯终端、离线优先和可读性。排版、分页、缩放或输入处理的改动需增加有意义的回归用例，保持原文字符锚点。解析相关改动需要覆盖异常输入和资源限制。Windows 支持不能仅凭 macOS 测试宣布通过。

提交的贡献需有权按项目 MIT 许可证发布。不要引入来源不明的代码、字体、图标或书籍。依赖必须检查许可证、已知漏洞和维护状况。

---

Use Python 3.11+ and uv. Run `uv sync --frozen`, then the tests, static checks and release gate documented in the README. Dependency updates must refresh `uv.lock` and repeat vulnerability and license checks.

For bug reports, include the OS, terminal, Python version, terminal columns/rows and reproduction steps. Supply minimal original, synthetic or explicitly redistributable text. Never upload libraries, commercial books, chat history, raw terminal captures, environment variables, credentials or screenshots with personal paths. Keep terminal diagnostic outputs local.

Preserve the terminal-only, offline-first reading experience. Layout, paging, resizing and input changes need meaningful regression coverage and stable source-character anchors. Parser changes require malformed-input and resource-bound tests. macOS results do not establish native Windows support.

Contribute only material you can license under MIT. Do not add code, fonts, icons or books of uncertain origin. Review every new dependency for licensing, known vulnerabilities and maintenance.


终端输出兼容层 `modu/terminal_render.py` 对接固定版本 Textual 6.12.0 的 compositor。升级 Textual 时必须复核其整屏/局部输出接口，并运行三个字宽模型的测试，不能仅依赖 headless 截图。

The terminal output adapter targets Textual 6.12.0's compositor. When upgrading Textual, review its full/partial update interfaces and rerun all three independent width-policy regressions. Headless snapshots alone cannot validate terminal cursor advances.
