# 实测记录 / Validation record

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
