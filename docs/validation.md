# 实测记录 / Validation record

## 1.2.0b8 — 章节分页与光标隐藏 / Chapter pages and cursor hiding

2026-11-07。Python 3.11 / 3.14 各 106 项测试通过。

- 默认开启「章节另起一页」；中英文设置在 42、59、70、84、110 列完整显示。开关按书库保存，切换和重启保留阅读位置。
- 16 组排版回归覆盖开启/关闭、两种段间距、四组宽高，逐字符按顺序比较，检查短章节、连续标题、长标题和页数；滚轮跨章、反向翻页及边翻页边缩放另有回归。
- 源码与实际安装命令 1.1.8 的独立真实 PTY 验收：4 章、7 页、2,511 个非空白字符，零重复、零遗漏；章首页首、五种设置宽度、开关保存和两次退出续读通过。
- 实际安装命令英文短篇回归：9 页、3,504 个非空白字符，零重复、零遗漏；26 次语言切换、18 次缩放、八主题、四个弹窗和退出续读通过。

English: 106 tests passed on each Python version. Chapter breaks default to on and are saved per library. Sixteen layout combinations check exact ordered source coverage and page counts, including short chapters, consecutive headings and long titles. UI regression covers wheel boundaries, reverse paging, resizing and both setting languages. Independent real-PTY acceptance passed for both source and installed 1.1.8: four chapters, seven pages and 2,511 non-whitespace characters with no duplication or loss; chapter starts, five settings widths, toggle persistence and resume passed.

The installed-command English regression also passed: nine pages, 3,504 non-whitespace characters, no duplication or loss, 26 language changes, 18 resizes, eight themes, four dialogs and resume.

### 原生光标 / Native cursor

- 旧版负对照：独立终端解码器模拟宿主重置 DECTCEM、将原生光标设为可见后，应用收到 FocusOut 仍未恢复隐藏，测试失败。
- 修复版真实 CLI PTY：12 轮 FocusOut/FocusIn、3 次无事件重置、搜索和导入输入框内的焦点切换均通过；共 31 次恢复。源码最长 0.449 秒，实际安装版最长 0.475 秒。
- 加入章节分页后的本机 1.1.8 再次通过 31 次光标恢复，最长 0.453 秒。
- 正文位置不变，两个输入框均可继续输入，退出后 shell 原生光标恢复。暂停、停止、关闭和无界面测试模式不抢占终端光标。
- 独立 xterm.js 6.0.0 DOM 回放：31 次负对照光标确实可见；33 个恢复/输入帧均未绘制原生终端光标。
- 使用者重启本机 1.1.7 后，在目标 Codex 桌面终端来回切换窗口，确认“已隐藏，切换窗口后正常”。宿主窗口未被自动化控制。

English: An old-version control fails after the independent terminal decoder simulates the host resetting native-cursor visibility. Real PTY acceptance covers 12 focus cycles, three missing-event resets, two input dialogs, an unchanged reading anchor and cursor restoration on exit. The installed 1.1.7 build recovered within 0.475 seconds; 1.1.8 passed again within 0.453 seconds. A separate xterm.js DOM replay verifies 31 visible negative controls and 33 frames without a native cursor after recovery. The user also confirmed the fix in the actual desktop host after restarting local version 1.1.7.

```sh
uv run python tests/acceptance_cursor.py --work ./test-artifacts/cursor
uv run python tests/acceptance_chapters.py --work ./test-artifacts/chapters
```

## 1.2.0b7 — 英文全文与产品截图 / Full English text and product images

2026-11-07。本地验收使用 O. Henry 的 *The Gift of the Magi*（《The Four Million》，1906）。[Project Gutenberg 书目](https://www.gutenberg.org/ebooks/2776)标注为美国公版；[原文来源](https://www.gutenberg.org/files/2776/2776-h/2776-h.htm)。验收提取该篇的 44 个段落，添加书名和作者行，共 2,068 个以空白分隔的词项、11,246 个原文字符。原文留在隔离测试目录，没有收入公开仓库或截图。

归一化验收文件 SHA-256：`61e4593492a04322644360ea58b6ca722404019c8c8e4968c208908cd6816ad1`。

| 实测 | 结果 |
| --- | --- |
| Python 3.11 / 3.14 | 各 87 项测试通过；发布图片篡改与未知图片拒绝测试通过 |
| 110 列真实 tmux 终端 | 全文 9 页，逐行核对原文与内部空格；零重复、零漏字 |
| 84 列独立 CLI / ANSI 解码 | 全文 13 页、9,134 个非空白字符；34 次语言切换、18 次缩放、八主题、续读通过 |
| 60 列独立 CLI / ANSI 解码 | 全文 12 页、9,134 个非空白字符；32 次语言切换、18 次缩放、八主题、续读通过 |
| 交互回归 | 25 次缩放、滚轮、右侧拖动、约两秒隐藏、搜索 Della、书签、目录和退出续读通过 |
| 英文断行 | 旧版能复现 don’t / you’ll 等缩写从撇号处拆开；修复后 24/32/40/48/64/80 列整篇普通单词和缩写不被拆开 |
| 中文回归 | 原创长文本 99 页、53,647 字符，零重复、零漏字；25 次缩放、八主题、滚轮、拖动、隐藏、搜索、书签、目录和续读通过 |
| 发布检查 | Ruff、Bandit、独立密钥扫描与文件白名单通过；锁定的运行依赖未检出已知漏洞 |

84 列会显示目录侧栏，60 列会隐藏侧栏，因此两种尺寸的正文有效宽度不同，页数不必随总窗口宽度单调变化。页码按当前实际正文区域重算。

English: the complete public-domain short story was validated locally at 60, 84 and 110 columns. Real terminal coverage found no duplicated or omitted characters; a separate tmux check also compared internal spaces and source slices, with mouse, search, bookmarks, 25 resizes and resume. The old wrapper split apostrophe contractions; the fix keeps ordinary Latin words, contractions and accents intact while allowing tokens longer than a whole line to break. The 84-column viewport includes a sidebar, so its effective text width and page count differ from the 60-column viewport without one. The downloaded story is not bundled; see [original-sample product images](product-images.md) and [environment verification](terminal-environments.md).

87 tests passed on each of Python 3.11 and 3.14. Chinese full-book regression also passed: 99 pages / 53,647 characters with no overlap or omission, 25 resizes and all eight themes. Ruff, Bandit, an independent secret scan and the release allowlist passed; the locked runtime dependencies had no known vulnerabilities reported by pip-audit at the time of this check. These are local results, not native Windows/Linux acceptance.

The test command accepts a separately obtained local book / 可使用单独取得的本地书籍复现：

```sh
uv run python tests/acceptance_language.py --book /path/to/story.txt --columns 60 --work ./test-artifacts/english-60
uv run python tests/acceptance_pty.py /path/to/story.txt --query Della --work ./test-artifacts/english-full
```


## 1.2.0b6 — 双语界面与设置按钮 / Bilingual UI and settings button

2026-11-07，macOS 本地验证。Python 3.11 / 3.14 各 75 项测试通过。

- 中英文书架、搜索、导入、书签、帮助、设置、主题名称、页码、提示和 CLI；语言按书库保存，`--help` 无需创建书库。
- 原文内容、当前字符锚点、书签、主题、翻页历史和书架选择在切换后保持一致；搜索输入 `l` 不会触发切换。
- 实际安装命令独立 PTY 验证：原创短篇 5 页 / 1,233 个非空白字符，零重复、零遗漏；18 次语言切换、18 次缩放、八主题、四个英文弹窗，以及退出后语言和位置恢复。
- `Settings s` 换行负对照已复现：Textual 按钮文字变更只触发重绘，未重算旧的中文宽度。现在显式请求按钮重新布局；42、59、60、69、70、84、85、110 列逐个检查所有可见按钮完整显示在一行。实际 PTY 同时检查 85/110 列切换前后，设置按钮必须完整出现在同一终端行。
- 另外将已安装命令从中文切换英文的原始 PTY 输出放入独立 xterm.js 6.0.0 DOM 渲染器，检查 `Settings s` 的实际文字边界、单行及右侧不裁切。此浏览器只作测试，不是应用运行方式，也没有访问宿主界面。

English: 75 tests pass on each of Python 3.11 and 3.14. Real installed-CLI acceptance covers 5 pages / 1,233 non-whitespace characters without overlap or gaps, 18 language switches, 18 resizes, eight themes, four English dialogs, and persistent language/reading position. A failing control reproduced the split `Settings s` label after switching languages; requesting button layout fixes its cached width. Tests inspect complete one-line labels at responsive breakpoints, and a separate xterm.js DOM replay checks the actual toolbar bounds. Book text is never translated or sent anywhere.

Reproduce the independent terminal test / 复现独立终端测试：

```sh
uv run python tests/acceptance_language.py --work ./test-artifacts/language
```

## 1.2.0b5 — 先前分页、主题与轨道基线 / Earlier paging, theme and rail baseline

版本 1.2.0b5；2026-11-07；macOS 26.6 arm64。公共素材均为原创或合成内容。

| 检查 | 结果 |
| --- | --- |
| Python 3.14 / 3.11 | 各 70 项测试通过 |
| 原创整本 PTY 核对 | 99 页、53,647 字符，非空白字符零重复、零遗漏 |
| 全文 PTY 交互 | 25 次缩放、八主题、滚轮、拖动、两秒隐藏、搜索、书签、目录、退出续读通过 |
| 标准字宽 PTY 轨道专项 | 151 帧、11,817 个轨道和留白单元格；121 次滚轮事件、21 次缩放、八主题，未检出单元格错位或残留 |
| 已安装命令的独立验证 | 原创短篇 5 页、1,233 个非空白字符，零重复、零遗漏；八主题、页码、三次缩放保持页首和退出续读通过，无诊断 App 子类 |
| xterm.js 6.0.0 DOM 像素回归 | 回放实际 PTY 输出，13/18/22 三个字号，保留修复与去掉修复的负对照；允许最大 1.25 CSS 像素的测宽取整误差 |
| 目标内置终端 | 使用者重启对应安装版 1.1.3 后，确认“右侧已对齐，隐藏正常” |

## 连续翻页、缩放和页码

b5 取消了旧版主动保留的一行重叠。整本检查除遗漏外，也统计重复出现的原文字符。缩放回归曾检出旧实现将页首从目标字符退回行首；现在裁去目标前的前缀，保持原文位置，并处理段落空行和末页边界。

页码按当前排版计算，在后台逐段统计行数；完整索引最多保留三组，不占用阅读视口的段落缓存。测试覆盖当前页递增、改变宽度和高度后重新计数、取消过期任务、末段不产生多余空白页，以及主题退出续读。窄窗口侧栏直接使用 Resize 事件携带的新宽度，避免比实际尺寸慢一次更新。八款配色的正文对比度均至少 7:1，辅助文字和强调色相对背景至少 4.5:1；这些是 sRGB 数值检查，不是对个人视觉舒适度的保证。

主题设计参考成熟阅读器区分浅色、暖纸和深色阅读背景的做法，颜色为项目自行选择：[Kobo 阅读外观](https://help.kobo.com/hc/en-us/articles/35996239522967-Kobo-Web-Reader-Navigation-Reading-Features)、[Apple Books 主题](https://support.apple.com/en-ie/guide/iphone/iphc1af7c57/27/ios/27)。

## 为什么之前的验证没有发现问题

之前只核对 ANSI 单元格，无法检出终端渲染层的字体测宽错误。xterm.js 的 [已知问题 #6058](https://github.com/xtermjs/xterm.js/issues/6058) 描述了高度吻合的现象：DOM 渲染器按连续标点测宽时触发 Chromium 的标点压缩，单个标点实际绘制时又使用全宽，导致右侧内容随标点数量偏移。

本次修复在终端输出阶段为非 ASCII 标点加上零单元格的 U+2060，保持测量与绘制的上下文一致。它不会写入原书、解析缓存、搜索文本或阅读位置。终端复制出来的显示文本可能包含这个字符。

独立实验在 xterm.js 6.0.0 的 DOM 渲染器和本机 Chromium 156 中复现了旧输出的数十至百余像素偏移。修复后的轨道与纯 ASCII 参考行的最大差异约 1.1 CSS 像素，属于该渲染器按 32 个字符取整测宽留下的误差；不宣称所有行像素坐标完全相同。目标宿主并未被自动控制或截图，它的最终画面由使用者单独确认。

b3 的左侧布局曾被使用者确认有效；b4 在输出端规避标点测宽问题后恢复右侧。旧 b1/b2 的单元格测试不能替代像素验证。Windows/Linux 的 CI 已配置，尚未远程运行或完成原生终端验收。

标准解码器对 U+2060 按零单元格处理，避免 pyte 0.8 遇到不可见格式字符时截断后续文本；像素回归始终接收原始字节，不做这种预处理。

## 可复现的像素回归

这是开发时的独立终端模拟器测试，MODU 程序仍为 Python/Textual CLI，没有引入浏览器或 WebView 运行依赖。只使用生成的标点样本；输出目录被 Git 忽略，可能包含可见正文，禁止使用私人书籍作为公开测试产物。

先采集真实 PTY 帧：

```sh
uv run python tests/acceptance_scrollbar.py --python .venv/bin/python --work ./test-artifacts/rail-pixels --capture-frames
```

安装固定版本的可选测试工具，在独立浏览器进程中回放。以下浏览器路径为 macOS Chrome 的标准应用路径；其他环境应提供自己的 Chromium 可执行文件。

```sh
npm install --prefix ./test-artifacts/pixel-tools --no-audit --no-fund @xterm/xterm@6.0.0 playwright-core@1.65.0
node tests/acceptance_pixels.cjs --frames ./test-artifacts/rail-pixels/frames.json --modules ./test-artifacts/pixel-tools/node_modules --browser "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --work ./test-artifacts/pixels
```

回放阻止网络请求，不使用个人浏览器配置；仅运行本地安装的测试引擎。检查包括显示与隐藏的轨道、缩放和主题。旧输出必须在同样的 1.25 CSS 像素阈值下失败，带保护字符的输出必须通过。结果 JSON 不保存正文；输入帧和原始终端转储仍属于本地诊断材料。

---

Version 1.2.0b5, validated on macOS with Python 3.14 and 3.11: 70 tests each. The original-book PTY check covers 99 pages / 53,647 characters with no duplicated or missing non-whitespace characters, 25 resizes, all eight themes, mouse controls, search, bookmarks, chapters and resume.

Earlier ANSI cell checks could not detect glyph measurement drift in the terminal's DOM renderer. The output now adds a zero-cell U+2060 after non-ASCII punctuation to avoid the contextual punctuation-spacing problem described in xterm.js issue #6058. Books, parsed text, search and source anchors are unchanged. Text copied from the terminal may include the output guards.

The optional test above replays real PTY frames in an isolated xterm.js 6.0.0 DOM renderer under Chromium 156 at 13/18/22 px, with network requests blocked. Removing the guard is a failing negative control. The fixed output retains at most about 1.1 CSS pixels of width-cache rounding relative to an ASCII reference, within the explicit 1.25 px tolerance; this is not a claim of pixel-identical coordinates. The user separately confirmed alignment and clean hiding of the right rail in the target embedded terminal using installed version 1.1.3. No automatic control or screenshot of that host was performed. These browser tools are optional test dependencies, never application dependencies. Windows/Linux native terminal acceptance remains pending.
