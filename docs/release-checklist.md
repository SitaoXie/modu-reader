# 发布检查 / Release checklist

此目录是候选源码，不包含个人安装配置。不要把工作区、上级 outputs 目录、旧交付包、书库或验收转储整体发布。

1. 检查源码、历史、许可证、依赖和原创素材来源。新仓库使用干净历史；确认提交作者信息是愿意公开的身份。
2. 执行 `uv sync --frozen`、`uv run pytest -q`、`uv run ruff check .`、`uv run bandit -r modu`。
3. 导出锁定运行依赖并执行 `pip-audit`；依赖升级后重跑测试。使用独立 secret scanner 复核，人工分类误报，不自动忽略所有发现。
4. 在隔离书库执行 README 的 PTY 回归。Windows、Linux、macOS 的原生终端体验分别记录，未测项目明确标注。
5. `uv build`，随后 `uv run python tools/normalize_sdist.py dist` 归一化所有者和扩展元数据，然后 `uv run python tools/check_release.py . dist/*.whl dist/*.tar.gz`。在新环境安装 wheel 并验证命令、导入、阅读和退出续读。wheel 不得包含测试驱动和正文诊断。
6. 检查源代码压缩包和 sdist 的完整文件清单；禁止个人路径、密钥、书籍、历史数据库、截图转储和其他产品配置。保留校验和。检查 tar/zip 所有者、扩展头和注释等元数据；发布门禁会拒绝未归一化的 sdist，避免构建机用户名泄露。
7. 创建公开仓库前确定仓库名、维护身份、安全联系渠道并启用私密漏洞报告。检查 CI 令牌仅有只读权限；禁止自动发布和隐式上传测试产物。
8. 仅公开已检查的候选目录/发布包。发布 GitHub、PyPI 或签名发布是单独的操作。

---

This directory is candidate source, without personal installation configuration. Never publish the parent workspace, outputs directory, old private delivery, library or terminal captures wholesale.

1. Review source, history, licenses, dependencies and provenance. Start with clean history and a commit identity you intend to make public.
2. Run frozen environment setup, pytest, Ruff and Bandit as above.
3. Export locked runtime dependencies and run pip-audit. Repeat tests after updates. Use a separate secret scanner and manually classify findings; do not blanket-ignore them.
4. Run isolated PTY regression tests. Record native Windows, Linux and macOS terminal acceptance separately; identify untested platforms.
5. Build with `uv build`, normalize source archive metadata with `uv run python tools/normalize_sdist.py dist`, inspect every wheel/sdist, then install the wheel in a clean environment and verify the CLI, import, reading and resume. Wheels must exclude diagnostic drivers.
6. Inspect the complete source archive and sdist file lists. Exclude personal paths, keys, books, history databases, screenshots/captures and unrelated tool configuration. Record checksums. Inspect owner fields, extended headers and comments; The release gate rejects unnormalized sdist ownership to prevent exposure of the build account.
7. Before creating a public repository, establish its name, maintainer identity and security contact, and enable private vulnerability reporting. Keep CI tokens read-only and avoid automatic publishing or diagnostic uploads.
8. Publish only inspected artifacts. GitHub/PyPI publication and signed releases are separate actions.


首次提交前在当前仓库执行 `git config --local user.useConfigOnly true`，再显式配置愿意公开的作者名与本人 GitHub 提供的 noreply 邮箱。不要让 Git 从本机用户名、主机名推断提交身份。更改配置不改写历史提交；作者、提交者、时间、签名及提交说明都需要复核。

Before the first commit, set `git config --local user.useConfigOnly true` and explicitly choose a public author name and the noreply email issued for your own GitHub account. Do not derive identity from the machine account/hostname. New configuration does not rewrite old commits; review author, committer, timestamps, signatures and messages. See [GitHub email documentation](https://docs.github.com/en/account-and-profile/concepts/email-addresses).

## 仓库介绍与首次体验 / Discovery and first use

官方仓库为 [SitaoXie/modu-reader](https://github.com/SitaoXie/modu-reader)。仓库简介、相关 Topics 与私密漏洞报告已配置；尚未发布到 PyPI。下面保留传播与后续发布建议。

- 仓库名：`modu-reader`，与 Python 分发名一致；启动命令为 `modu`。
- 中文简介：`中英文终端阅读器：等代码、构建或编程代理运行时读两页。离线 TXT / EPUB / PDF / Markdown，自动续读。`
- English About: `A Chinese and English terminal ebook reader for spare moments while code, builds or agents run. Offline TXT/EPUB/PDF/Markdown.`
- Suggested GitHub topics: `terminal-reader`, `ebook-reader`, `tui`, `cli`, `chinese`, `epub`, `pdf`, `markdown`, `offline`, `textual`, `python`, `vibe-coding`.
- 在仓库名称、About 和 README 中自然使用准确关键词；不填无关热门标签，不承诺搜索排名。仓库公开后再补真实的 Repository、Issues、Changelog 链接到包元数据，禁止使用虚构地址。
- README 的试读使用 `examples/first-pages.txt` 与 `examples/first-pages.en.txt`（中英文原创短篇）；`examples/river.txt` 是重复段落组成的长篇回归素材，适合压力测试。
- 发布演示可录制 20–30 秒：并排的开发工具和 MODU → 原创短篇翻页 → 收起目录/调整宽度 → 退出并续读。开发窗格只使用公开演示项目，录制前检查标题、路径、账号和通知；不要使用私人书籍或本人的聊天截图。没有真实通知接入时，不展示或暗示自动收到 AI 完工提醒。
- 首次传播可选题：`等 Codex 写代码时，我做了一个放在旁边的终端阅读器`；English: `Read a few pages while your coding agent works — MODU, a terminal ebook reader`。
- 先完成官方仓库与经过核验的 Release。确认包名归属并完成正式包发布后，才能把基于索引的安装命令放到 README；当前保留已验证的本地源码命令。

The official repository is [SitaoXie/modu-reader](https://github.com/SitaoXie/modu-reader), with About text, relevant topics and private vulnerability reporting configured. No PyPI release has been made. The remaining items are suggestions for future promotion and releases. Keep the package name, repository name and command easy to relate: `modu-reader` → `modu`. Use relevant topics and clear use cases, with no search-ranking promises. Add real project URLs only after the repository exists. The demo story is original; the longer fixture is for regression testing. Any preview should use a public demo workspace and original text, with no private paths, accounts, notifications or chats. Describe adjacent reading accurately; automatic agent-completion alerts are not implemented. Registry install instructions must wait until the official package has actually been published.

References: [GitHub README guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes), [GitHub topics](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics), [uv tool usage](https://docs.astral.sh/uv/guides/tools/).
