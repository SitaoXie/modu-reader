# 第三方许可 / Third-party notices

MODU 原创代码和原创文字为 MIT。下表来自锁定依赖的包元数据及其随包许可证；安装器从各项目发行包安装依赖，本仓库不复制它们的源码。若以后分发捆绑可执行文件，须重新收集所有实际捆绑组件的完整许可和版权声明。

MODU's original source and sample text use MIT. The table reflects the locked runtime packages' metadata and shipped licenses. Dependencies are installed from their distributions, not vendored here. A future bundled executable must include the full license/copyright notices of every bundled component and undergo a new review.

| Package | Locked version | License |
| --- | --- | --- |
| Textual | 6.12.0 | MIT |
| Rich | 15.0.0 | MIT |
| pypdf | 7.0.0 | BSD-3-Clause |
| Beautiful Soup | 4.15.0 | MIT |
| Soup Sieve | 4.0.1 / 2.10 (older Python 3.11 patch releases) | MIT |
| markdown-it-py | 4.2.0 | MIT |
| mdit-py-plugins | 0.6.1 | MIT |
| mdurl | 0.1.2 | MIT |
| linkify-it-py | 2.2.0 | MIT |
| Pygments | 2.21.0 | BSD-2-Clause |
| charset-normalizer | 3.5.2 | MIT |
| regex | 2026.9.29 | Apache-2.0 AND CNRI-Python |
| platformdirs | 4.14.5 | MIT |
| defusedxml | 0.7.1 | Python Software Foundation License |
| typing-extensions | 4.16.0 | PSF-2.0 |

[pypdf's license](https://github.com/py-pdf/pypdf/blob/main/LICENSE) is BSD-3-Clause. This candidate does not include or depend on PyMuPDF or MuPDF. [defusedxml](https://github.com/tiran/defusedxml) is used for restricted XML parsing.

开发测试工具不随 wheel 分发，按各自许可证使用；pyte（LGPL-3.0）和 pexpect（ISC）只用于本地终端验收，不是运行依赖。不要将开发虚拟环境直接打包作为应用发布。

Development tools are not included in the application wheel. pyte (LGPL-3.0) and pexpect (ISC) are used only for terminal testing, not at runtime. Never distribute the development virtual environment as the app.

可选像素回归使用 `@xterm/xterm` 6.0.0（MIT）和 `playwright-core` 1.65.0（Apache-2.0），由开发者单独安装到忽略的测试目录；不随源码或 wheel 捆绑，不属于应用运行依赖。浏览器使用开发者自己安装的 Chromium 可执行文件。

Optional pixel regression uses separately installed `@xterm/xterm` 6.0.0 (MIT) and `playwright-core` 1.65.0 (Apache-2.0). Neither package nor a browser is bundled in the source archive or wheel, and neither is an application runtime dependency.

独立终端产品图中的中英文短篇均为项目原创素材，英文文本译自项目自己的中文短篇，随 MIT 许可证提供。开发验收单独使用 O. Henry 的公版短篇，原文不随本仓库分发；来源与验证范围见 [实测记录](docs/validation.md)。截图工具复用上述可选 xterm.js/Playwright 开发依赖，不新增运行依赖。

Chinese/English text in the isolated-terminal product images is original project material; the English story translates the project's own Chinese example and is provided under MIT. Separate local acceptance used an O. Henry public-domain story without distributing it here; see the [validation record](docs/validation.md). Image tools reuse the optional xterm.js/Playwright development dependencies above and add no runtime dependency.

使用者提供的桌面预览包含第三方应用界面与公版原文，不标为项目原创。

User-supplied desktop previews include third-party application UI and public-domain text, not project-original material.
