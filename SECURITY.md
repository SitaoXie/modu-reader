# 安全与隐私 / Security and privacy

生词、译文和查询过的音标保存在本机书库数据库。在线翻译模式将所选英文单词发送给有道查询音标，本地翻译模式需主动点击查询。英、美发音按钮把原文发送给有道获取音频，翻译选项中也提供本地浏览器语音；终端使用系统播放器或本地语音进程，通过独立参数或标准输入传值，不执行 shell 命令。临时音频在播放结束或取消后清理。

Vocabulary, meanings and retrieved IPA are stored in the local library database. Online translation sends selected English words to Youdao for IPA lookup. On-device translation requires an explicit lookup. British and American speaker buttons send the original text to Youdao for audio. Local browser pronunciation is available in translation options. The terminal uses system audio or speech processes with argument arrays or stdin, without a shell. Temporary audio is removed after playback or cancellation.

MODU 在本机复制和解析明确选择的书籍。不包含遥测、书中脚本执行或自动更新。Web 阅读会在本机回环地址开启临时服务，按会话限制访问，书中资源仅从书库读取。PDF.js 和本地翻译模型按需从其发行方下载。翻译默认在本机处理。选择在线引擎后，翻译请求仅把选区和语种通过 HTTPS 发给有道或 Google。SQLite 语句使用参数绑定；缓存不使用 pickle；导入不使用 shell。

解析在独立 Python 进程中执行，限制输入、输出、EPUB 解压内容、PDF 页数及运行时间。XML 禁止 DTD 和外部实体；文件名与正文剥离终端控制字符及双向覆盖控制符。缓存采用有界解压、格式校验和原子写入。书库在创建时使用当前平台适用的私有权限。

这些措施降低风险，但不是操作系统安全沙箱。第三方解析器仍处理复杂输入；Windows 没有 POSIX 的地址空间限制；已有目录的权限不会被强制收紧；书库不加密。同一用户下的恶意本地程序不在防护边界内。只导入来源可信的文件。程序运行离线不等于不存在解析器漏洞。

发布前必须运行静态检查、依赖漏洞审计、敏感信息扫描和实际发布包检查；扫描只能覆盖其规则与当时已知漏洞，不能证明绝对安全。开发依赖与运行依赖分开管理。

仓库已启用 [GitHub 私密漏洞报告](https://github.com/SitaoXie/modu-reader/security/advisories/new)，请通过该渠道向维护者报告安全问题。不要在公开 issue 上传可利用样本、私人书籍、书库或凭据。

---

MODU copies and parses explicitly selected local books. It has no telemetry, book-script execution or automatic updater. Web reading uses a temporary loopback service with session-scoped access. Book resources come from the local library. PDF.js and local translation models download on demand from their distributors. Translation runs on the device by default. Choosing an online engine sends only the selection and language codes to Youdao or Google over HTTPS when translating. SQLite uses bound parameters; caches do not use pickle; imports do not invoke a shell.

Parsing runs in a separate Python process with limits on input/output size, EPUB expansion, PDF pages and execution time. XML DTDs/external entities are forbidden. Terminal controls and bidi override controls are stripped. Cache reads use bounded decompression and schema validation; writes are atomic. Newly created library directories use platform-appropriate private permissions.

These mitigations are not an OS security sandbox. Third-party parsers process complex inputs; Windows lacks the POSIX address-space limit; existing directory permissions are not tightened; libraries are not encrypted. Malicious programs already running as the same local user are outside this boundary. Import trusted files only. Offline operation does not eliminate parser vulnerabilities.

Before release, run static checks, dependency vulnerability auditing, secret scanning and inspection of the actual distribution files. Scans cover their rules and currently known advisories; they do not prove absolute safety. Development and runtime dependencies are managed separately.

[GitHub private vulnerability reporting](https://github.com/SitaoXie/modu-reader/security/advisories/new) is enabled. Use that channel to contact the maintainer about security issues. Do not post exploit samples, private books, library databases or credentials in public issues.
