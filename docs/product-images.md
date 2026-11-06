# 产品图来源 / Product image provenance

这些图片来自实际运行的 MODU 命令。开发工具在隔离书库启动真实 PTY，保存终端输出，再用独立的 xterm.js 6.0.0 DOM 终端渲染并截图。图中没有构造的阅读器界面、私人书库、宿主窗口、个人终端配置或真实 AI 对话。MODU 本身仍为 Python/Textual TUI；浏览器仅用于开发验收。

These images capture actual MODU command output. Developer tools start real PTYs with isolated libraries, then render the recorded output in an independent xterm.js 6.0.0 DOM terminal. The reader UI is genuine. Images use original project text and contain no personal libraries, host windows, shell profiles or AI conversations. MODU remains a Python/Textual TUI; the browser is a developer capture tool.

| 图片 / Image | 内容 / Contents |
| --- | --- |
| [reading-english.png](images/reading-english.png) | 英文原创《The Riverside Bookshop》、黑金主题、110 × 34 单元格 / Original English story, black/gold theme, 110 × 34 cells |
| [reading-chinese.png](images/reading-chinese.png) | 中文原创《河岸书店》、纸笺主题、110 × 34 单元格 / Original Chinese story, light paper theme, 110 × 34 cells |
| [side-by-side.png](images/side-by-side.png) | tmux 实际分屏：源码改动摘要与本地 pytest 输出 / MODU，148 × 34 单元格 / Real tmux split: source diff summary and local pytest output / MODU, 148 × 34 cells |

正文分别来自 `examples/first-pages.txt` 与 `examples/first-pages.en.txt`，均按项目 MIT 许可证提供。截图中的书名通过演示文件名设置。英文公版短篇只用于单独的本地验收，不出现在这些图片中，也不随仓库分发。

Text comes from the MIT-licensed original examples `examples/first-pages.txt` and `examples/first-pages.en.txt`. Demo filenames provide the displayed book titles. The public-domain English short story used in separate acceptance tests is not included in these images or distributed with the repository.

## 复现 / Reproduce

需要 POSIX 环境、`tmux`、项目开发依赖及开发者自己安装的 Chromium。使用新的测试目录。以下工具从不调用个人应用截图接口；渲染进程不使用个人浏览器配置，并阻止网络请求。

Requires POSIX, `tmux`, the project's dev dependencies, and your own Chromium executable. Use a new work directory. The capture renderer uses a separate browser process, blocks network requests and does not access personal browser profiles or host windows.

```sh
uv run python tools/capture_product.py --work ./test-artifacts/product
npm install --prefix ./test-artifacts/pixel-tools --no-audit --no-fund @xterm/xterm@6.0.0 playwright-core@1.65.0
node tools/render_product.cjs --frames ./test-artifacts/product/frames.json --modules ./test-artifacts/pixel-tools/node_modules --browser "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --output ./test-artifacts/product-images
```

公开前检查每张图，确认没有个人信息。PNG 仅保留像素所需的 IHDR、IDAT、IEND 块；没有文本、EXIF 或额外尾部数据。发布检查只接受 `tools/check_release.py` 中按文件名和 SHA-256 固定的已复核图片，不放宽到任意 PNG。更新截图需重新完成视觉和元数据检查，再更新校验值。原始 PTY 记录、测试书库和浏览器依赖留在被忽略的测试目录。

Review every image before publishing. Approved PNGs contain only IHDR, IDAT and IEND chunks, with no text, EXIF or appended data. The release gate pins reviewed filenames and SHA-256 hashes instead of allowing arbitrary PNGs. New captures require fresh visual/metadata review and updated hashes. Raw terminal recordings, libraries and browser dependencies remain in ignored test directories.
