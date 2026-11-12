# 更新记录 / Changelog

## 1.3.0b8 — 两端功能补齐 / Terminal and Web parity

终端增加拖选翻译、可选松手自动翻译、英美音标和发音、生词收藏切换、译文编辑及正文标注，复用 Web 的引擎与语言偏好。Web 增加全书搜索、正文宽度、三档段间距和章节另起页开关；关闭时保留章节样式并按需连续加载。PDF 搜索使用原页文字层，排版设置只作用于可重排格式。

The terminal adds mouse selection translation, optional automatic lookup, UK/US IPA and audio, vocabulary toggling, meaning edits and inline saved-word marks, using the Web reader's engine and language preferences. Web adds full-book search, reading width, three paragraph spacings and chapter breaks. Continuous mode retains scoped chapter styles and loads subsequent chapters on demand. PDF search uses its original text layer; layout controls apply to reflowable formats.


## 1.3.0b7 — 收藏切换 / Vocabulary toggle

词卡上的收藏按钮支持再次点击取消，正文标注同步更新。新译词、已保存词和手动翻译使用相同交互。

Click the saved-word button again to remove the entry and its highlights. Newly translated words, cached words and manual translation use the same toggle.

## 1.3.0b6 — 词典卡片 / Dictionary cards

翻译浮层使用单词、英美音标、喇叭图标和译文的层级排版。增加真实音标查询与本地缓存，英、美发音分别播放对应音频。折叠翻译选项，精简收藏与生词列表布局。

Translation cards now show the word, British and American IPA, speaker icons and meaning. IPA lookups are cached locally, and each speaker plays its corresponding accent. Translation options are collapsible, with compact save controls and a clearer vocabulary list.

## 1.3.0b5 — 生词本与发音 / Vocabulary and pronunciation

修复升级过程中界面与旧服务混用导致设置报错，服务启动时固定界面资源。增加本地生词本、原文发音和英文有道发音。保存过的单词跨书籍标注，可点击查看译文，支持修改与删除。

Freeze reader assets at startup to keep the interface aligned with the running server after an upgrade. Add local vocabulary, browser pronunciation and explicit Youdao audio for English. Saved words are highlighted across books with quick lookup, editable meanings and deletion.

## 1.3.0b4 — 自动划词翻译和图片放大 / Selection translation and image zoom

Web 设置增加松手后自动翻译，以及有道、Google 和本地 Argos 三种引擎。点击 EPUB 插图或封面可打开大图、缩放并恢复适应窗口。

Web settings now offer translation on pointer release and a choice of Youdao, Google, or on-device Argos. Click an EPUB illustration or cover to open it, zoom in, or fit it to the window.

## 1.3.0b3 — Web 连续翻页 / Continuous Web paging

左右翻页按当前视口推进，读完本节或本张 PDF 原页才跨页。短末屏从上一屏之后开始，向左可回到刚读过的页首。

Left and right turn one visible screen at a time. The reader finishes the current section or PDF sheet before moving on. Short final screens start at the first unread line, and Back returns to the previous screen.

## 1.3.0b2 — 侧边浏览器入口 / Side browser entry

`modu --serve` 提供固定的本机阅读地址 `http://127.0.0.1:8765`，可用 `--port` 更改端口。

`modu --serve` serves the reader at `http://127.0.0.1:8765`. Use `--port` to choose a different port.

## 1.3.0b1 — Web 阅读与划词翻译 / Web reading and selection translation

- 增加 `modu --web` 和 `modu --browser`，保留 EPUB 原书样式、插图和目录，按原页渲染 PDF。
- 选中文字即可翻译，无需账户。目标语言依次采用单本设置、全局设置、系统语言。模型首次使用时下载。
- Windows 终端停止输出可能被计作一格的标点辅助字符，修复正文和帮助边框错位。

English: adds a Web reader with EPUB publication styles and navigation, original PDF pages, and on-device selection translation. Book settings override the global target, which follows the system by default. Windows terminal output omits a punctuation helper that could occupy a cell and misalign the reader.


## 1.2.0b10 — 导入副本说明 / Import copy information

- 中英文导入窗口和命令行明确说明：导入创建独立副本，成功后修改、移动或删除原文件均不影响阅读，后续更改不会自动同步。
- 显示当前书库的实际副本目录，支持自定义书库。窄窗口可滚动查看完整说明与长路径，输入框和操作按钮保持可见。
- 验证原文件修改、移动和删除后仍可阅读，并覆盖移除缓存后从书库副本重建的情况。

English: import dialogs and CLI output explain independent library copies, display the active storage directory and clarify that later source changes are not synced. Narrow dialogs keep input and buttons accessible while longer notes and paths can scroll. Regression verifies reading after source edits, moves or deletion, including cache rebuilds from the library copy.

## 1.2.0b9 — 书架管理与终端交互修复 / Library management and terminal interaction

- 书架新增归档、恢复和删除；操作需二次确认，默认选中取消。归档保留书签和进度；删除只移除书库副本、缓存及阅读记录，保留原始导入文件。旧书库自动升级。
- 目录滑块改用整格背景色，消除细分方块字形造成的接缝；缩放或重新展开目录后保持当前章节可见。
- 窗口重新获得焦点时恢复鼠标上报；每 0.5 秒补充恢复，覆盖宿主同时丢失焦点通知的情况，不重绘正文。
- 保留鼠标禁用选项和已协商的像素坐标模式，长按拖动不中断；失焦时释放未完成的拖动，避免滑块继续捕获按钮点击。
- 新增真实 CLI PTY 与独立 xterm.js DOM 的实时交互回归，由终端实际产生滚轮、点击和拖动事件；旧版在相同模式重置后无法恢复。

English: adds archive, restore and delete actions with confirmation and Cancel selected by default. Archives retain bookmarks and progress; deletion removes only library copies, caches and reading data, preserving original imports. Existing libraries migrate automatically. TOC scrollbars use solid cells to avoid fractional-glyph seams, and the current chapter stays visible after resizing. Restores mouse reporting on focus and every 0.5 seconds without repainting, including missing-focus cases; preserves held drags and releases interrupted capture. Adds live CLI PTY/xterm.js regression with an old-version failure control.

## 1.2.0b8 — 章节分页与光标修复 / Chapter pages and cursor recovery

- 新增默认开启的「章节另起一页」设置：每章从新页开始，章末留白，页数按章节重算；关闭后恢复连续排版。设置按书库保存，切换和缩放保留原文位置。
- 窗口切换与绘制前重新隐藏原生终端光标；无焦点通知时每 0.5 秒发送一次隐藏控制序列，不重绘正文。
- 保留 Textual 输入框光标；暂停应用时停止守护，退出后恢复 shell 光标。
- 增加独立真实 PTY 光标回归和使用者提供的中英文 Codex 桌面预览图。

English: adds “New page per chapter”, enabled by default, with chapter-aware page counts, saved preferences and stable source positions. Turning it off restores continuous layout. Reasserts native-cursor hiding on focus changes and drawing, with a 0.5-second control-only fallback. Textual input carets remain usable; the guard stops while suspended and the shell cursor is restored on exit. Adds real-PTY regression and user-supplied Chinese/English desktop previews.

## 1.2.0b7 — 中英文阅读与真实产品图 / Chinese and English reading

- 调整定位为中英文终端阅读器，面向等待代码、构建、测试或 AI 编程任务的碎片时间。根据官方资料区分终端能力与本项目实测范围。
- 修复英文缩写、带音标单词及普通长单词的断行；超过整行宽度的长串仍可换行，不丢原文字符。
- 修复 TXT 书名后紧接短章节名时被误判为作者的问题。
- 增加原创英文短篇、真实 PTY 产品截图及公开截图复现工具；本地完整验证 O. Henry 的公版短篇，原文不随仓库分发。

English: positions MODU as a Chinese/English reader for spare moments during code, build, test, or agent work. Keeps English contractions and accented words intact, corrects short chapter headings mistaken for authors, and adds an original English story plus genuine PTY product images. A complete public-domain English short story was validated locally without bundling its text.

## 1.2.0b6 — 双语界面 / Bilingual interface

- 新增英文书架、目录栏、搜索、书签、导入、设置、帮助、主题名称、页码和提示；书籍正文保持原文。
- 按 `l`、点击顶部语言按钮，或在阅读设置中切换；`--lang en/zh` 同时支持启动和命令帮助。语言选择按书库保存。
- 切换时保留当前原文位置、翻页历史、书签、主题及书架选择。窄窗口隐藏品牌和主题按钮，保留语言按钮；`t` 始终可用。
- 修复中英文切换后按钮沿用旧宽度的问题，`Settings s` 完整显示在一行；回归覆盖 42–110 列及布局临界宽度。
- 增加真实 PTY 双语验收，独立解码实际 CLI 输出，核对连续翻页、十八次切换、八主题、十八次缩放和退出续读。

English: adds English UI text across the shelf, dialogs, settings, theme names, page counts, notices and CLI. Switch with `l`, the top button, settings, or `--lang en/zh`; the choice is saved per library. Switching preserves source position, page history, bookmarks, theme and shelf selection. Real-PTY acceptance checks both languages and exact page continuity without app diagnostics.

## 1.2.0b5 — 连续分页、页码与主题 / Continuous pages, page counts and themes

- 取消前后页重叠一行；下一页从上一页之后的内容开始，全书末尾保持最后一页。
- 缩放保留页首的具体原文字符；段落空行恢复时不再回到上一段末行。返回上一页会复用同一版面下的已读边界。
- 底部显示当前页 / 总页数，按窗口宽度、高度及段间距计算；后台统计并保留最多三组行索引，翻页继续按需绘制。
- 新增旧书、竹影、晨雾、石墨和松夜，连同原有主题共八款。明暗模式、对比度、搜索高亮和设置保存一起验证。
- 整本回归同时统计重复和遗漏字符；增加缩放页首、段落空行、末页、页码和主题持久化检查。

English: removes the intentional one-line overlap between pages; preserves the exact first source character across resize and keeps the final page in place. Adds background page counting for the current terminal layout, plus five new palettes for eight total. Regression checks now reject duplicated as well as skipped source characters and cover page counts, gaps, resize and theme persistence.

## 1.2.0b4 — 右侧轨道与标点字距 / Right rail and punctuation spacing

- 阅读轨道恢复右侧。输出阶段为非 ASCII 标点添加零单元格的 U+2060，避免部分 DOM 终端对重复标点测宽时压缩字距；原书、换行、搜索和进度锚点保持原文。
- 新增真实 PTY 输出的 xterm.js DOM 像素回归，包含去掉修复的负对照、三个字号、主题和缩放；记录亚像素/像素取整误差，不以 ANSI 单元格正确代替画面测量。
- 使用者已在目标内置终端确认右侧对齐和自动隐藏正常。终端复制的显示文本可能带有零宽保护字符；原书文件不含程序添加的字符。
- 更新场景化双语 README，提供原创短篇试读和包关键词。

English: restores the right rail and adds a zero-cell U+2060 output guard after non-ASCII punctuation to avoid contextual spacing in affected DOM terminals. Source books and reading anchors are unchanged. A real PTY-to-DOM pixel regression includes an unfixed negative control and three font sizes. The user confirmed right alignment and hiding in the target embedded terminal. Text copied from the terminal may contain output-only guards. Also improves bilingual onboarding and adds an original demo story.

## 1.2.0b3 — 内置终端兼容 / Embedded-terminal compatibility

- 阅读轨道移到每行最左侧，在中文和目录之前，避免宿主整行字形绘制造成像素偏移。
- 保留拖动、滚轮、两秒隐藏与原文锚点续读。目标内置终端的使用者已确认对齐和隐藏正常。
- 完整检查 Git 对象与暂存内容；发布指引补充显式提交身份要求，避免自动推断本机用户名和主机名。

English: places the reading rail at the start of every line, before Unicode text and the chapter sidebar, to avoid host-level glyph shaping offsets. Dragging, scrolling, idle hiding and source-anchor resume are preserved. The user confirmed alignment and clean hiding in the target embedded terminal. Release guidance now requires explicit public commit identity.

## 1.2.0b2 — 终端轨道定位修复 / Terminal rail positioning

- 修复终端字宽与 Rich 判断不同时，整屏刷新将滚动条色块画到正文右边距的问题。
- 整屏与局部更新均为每段带样式的文字、留白和轨道显式定位；重绘 Unicode 区域前覆盖原有单元格。
- 加入标准、标点偏窄、歧义字符偏宽三种独立终端模型，以及能检出旧版故障的负对照测试。
- 覆盖 69/70 列侧栏临界值、84 列紧凑窗口、多次缩放、拖动、自动隐藏与退出续读。

English: fixes rail/padding drift when terminal glyph advances differ from Rich's measurements. Both full and partial updates explicitly position styled runs and clear allocated Unicode cells. Adds independent width-policy decoders, a failing old-renderer control, breakpoint resizing and mouse/resume regression coverage. The compatibility adapter is local to MODU; no system font settings or dependency source files are patched.

## 1.2.0b1 — 开源候选 / Open-source candidate

- 中英文 README、MIT 许可证、贡献和安全说明、发布检查工具。
- PDF 改用 BSD 许可的 pypdf；没有 PyMuPDF/MuPDF 依赖。
- 跨平台数据路径，Python console entry point，Windows/Linux/macOS CI 配置。
- 私有书库、导入快照、有界缓存、EPUB/XML 路径和实体防护、解析子进程超时。
- 生产运行删除正文诊断导出；所有测试使用原创或合成内容。
- 保留中文标点排版、独立 ASCII 色块进度条、左侧章节目录、主题和锚点续读。

English: adds bilingual documentation, MIT licensing, release checks and platform CI; switches PDF extraction to BSD-licensed pypdf; hardens imports and caches; removes production text diagnostics; replaces private test material with original fixtures. Preserves Chinese typography, the separate ASCII-space scrollbar, chapter sidebar, themes and source-anchor resume.

Native Windows/Linux acceptance and optional AI progress integration remain future work.
