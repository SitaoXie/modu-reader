// Turn one visible screen at a time while keeping the document's own layout.
const EPSILON = 1;

function caretAt(doc, x, y) {
  if (doc.caretRangeFromPoint) return doc.caretRangeFromPoint(x, y);
  const point = doc.caretPositionFromPoint?.(x, y);
  if (!point) return null;
  const range = doc.createRange();
  range.setStart(point.offsetNode, point.offset);
  range.collapse(true);
  return range;
}

class ScreenPages {
  constructor(node, surface, tailParent) {
    this.node = node;
    this.surface = surface;
    this.doc = node.ownerDocument;
    node.style.scrollBehavior = "auto";
    node.style.overflowAnchor = "none";
    if (tailParent) {
      this.tail = this.doc.createElement("div");
      this.tail.setAttribute("aria-hidden", "true");
      this.tail.style.cssText = "display:block!important;flex:none!important;height:0;min-height:0!important;max-height:none!important;margin:0!important;padding:0!important;border:0!important;clear:both;visibility:hidden;pointer-events:none";
      tailParent.append(this.tail);
    }
    this.layout = this.geometry;
  }

  get geometry() {
    return `${this.node.clientWidth}:${this.node.clientHeight}`;
  }

  get top() {
    return Math.max(0, this.node.scrollTop);
  }

  get height() {
    return this.node.clientHeight;
  }

  get extent() {
    return Math.max(this.height, this.node.scrollHeight - (this.tail?.offsetHeight || 0));
  }

  get end() {
    return this.cut ?? Math.min(this.extent, this.top + this.height);
  }

  get position() {
    const normalLimit = Math.max(1, this.extent - this.height);
    return {
      scroll: Math.min(1, this.top / normalLimit),
      offset: this.extent ? Math.min(1, this.top / this.extent) : 0,
    };
  }

  get viewport() {
    if (this.node === this.doc.scrollingElement) {
      return {top: 0, left: 0, width: this.node.clientWidth};
    }
    const rect = this.node.getBoundingClientRect();
    return {top: rect.top + this.node.clientTop, left: rect.left + this.node.clientLeft, width: this.node.clientWidth};
  }

  textAt(y) {
    const {left, width} = this.viewport;
    const ranges = [];
    for (const ratio of [0.03, 0.17, 0.37, 0.56, 0.77, 0.94]) {
      const range = caretAt(this.doc, left + width * ratio, y);
      if (range?.startContainer.nodeType !== 3) continue;
      const rect = range.getBoundingClientRect();
      if (rect.height > 0) ranges.push({range, rect});
    }
    return ranges;
  }

  setTop(value) {
    const extent = this.extent;
    const top = Math.max(0, Math.min(Math.round(value), extent - 1));
    if (this.tail) {
      // Leave enough trailing space for a short final screen to start at its
      // actual boundary instead of clamping back onto the previous screen.
      this.tail.style.setProperty("height", Math.max(0, Math.ceil(top + this.height - extent)) + "px", "important");
    }
    this.node.scrollTop = top;
  }

  prepare(end) {
    this.surface.style.clipPath = "";
    const top = this.top;
    const height = this.height;
    const {top: viewportTop} = this.viewport;
    const bottom = viewportTop + height;
    let edge = Math.min(this.extent, top + height);
    if (end !== undefined) {
      edge = Math.min(edge, end);
    } else if (edge < this.extent - EPSILON) {
      // Chromium can round a half-pixel probe onto the adjacent viewport.
      for (const {rect} of this.textAt(bottom - 2)) {
        if (rect.top < bottom && rect.bottom > bottom + 0.05) {
          const lineTop = Math.floor(top + rect.top - viewportTop);
          if (lineTop > top + EPSILON) edge = Math.min(edge, lineTop);
        }
      }
    }
    this.pageTop = top;
    this.cut = edge;
    const clip = edge < this.extent ? Math.max(0, Math.ceil(top + height - edge)) : 0;
    this.surface.style.clipPath = clip ? `inset(0 0 ${clip}px 0)` : "";
    // A retained caret locates the first displayed line after a width change.
    const first = this.textAt(viewportTop + 1).find(({rect}) => rect.bottom > viewportTop);
    this.anchor = first && {range: first.range, inset: first.rect.top - viewportTop};
    this.layout = this.geometry;
  }

  show(top, end) {
    this.setTop(top);
    this.prepare(end);
  }

  restore(position, endRatio) {
    const extent = this.extent;
    const top = Number.isFinite(position.offset)
      ? position.offset * extent
      : position.scroll * Math.max(0, extent - this.height);
    this.show(top, endRatio === undefined ? undefined : Math.round(endRatio * extent));
  }

  previous() {
    const end = this.top;
    this.setTop(Math.max(0, end - this.height));
    const {top: viewportTop} = this.viewport;
    let start = this.top;
    if (start > 0) {
      for (const {rect} of this.textAt(viewportTop + 0.5)) {
        if (rect.top < viewportTop && rect.bottom > viewportTop) {
          start = Math.max(start, Math.ceil(this.top + rect.bottom - viewportTop));
        }
      }
    }
    this.show(Math.min(start, Math.max(0, end - 1)), end);
  }

  releaseOnScroll() {
    if (this.pageTop === undefined || Math.abs(this.top - this.pageTop) <= EPSILON) return false;
    this.cut = this.anchor = this.pageTop = undefined;
    this.surface.style.clipPath = "";
    return true;
  }

  resize(position) {
    if (this.layout === this.geometry) return false;
    if (this.anchor?.range.startContainer.isConnected) {
      const rect = this.anchor.range.getBoundingClientRect();
      this.show(this.top + rect.top - this.viewport.top - this.anchor.inset);
    } else {
      this.restore(position);
    }
    return true;
  }

  dispose() {
    this.tail?.remove();
    this.surface.style.clipPath = "";
  }
}

const $ = id => document.getElementById(id);
const endpoint = path => new URL(path, import.meta.url);
const frame = $("book-frame");
const pdfView = $("pdf-view");
const dialog = $("dialog");
const selectionPreview = $("selection-preview");
const root = document.documentElement;
const strings = {
  search: ["搜索", "Search"], searchBook: ["搜索整本书", "Search the whole book"],
  searchHint: ["输入关键词，Enter 搜索", "Type a phrase, then press Enter"],
  searching: ["正在搜索全书…", "Searching the book…"], noResults: ["未找到匹配文字。", "No matching text."],
  searchResults: ["个结果", "results"], searchMore: ["显示前 200 个，请细化关键词。", "First 200 shown. Refine your search."],
  readingSettings: ["阅读排版", "Reading layout"], readWidth: ["正文宽度", "Reading width"],
  spacing: ["段间距", "Paragraph spacing"], compact: ["紧凑", "Compact"], relaxed: ["舒展", "Relaxed"], airy: ["宽松", "Airy"],
  chapterBreaks: ["章节另起一页", "Start chapters on a new page"],
  fixedLayout: ["PDF 保留原始页面，正文宽度、段间距和章节分页仅用于 EPUB、TXT 与 Markdown。", "PDF keeps its original pages. Width, spacing and chapter breaks apply to EPUB, TXT and Markdown."],
  import: ["导入", "Import"], theme: ["主题", "Theme"], settings: ["设置", "Settings"],
  shelf: ["我的书架", "My bookshelf"], archived: ["已归档", "Archived"],
  back: ["‹ 书架", "‹ Shelf"], contents: ["目录", "Contents"], marks: ["书签", "Marks"],
  previous: ["← 上一页", "← Previous"], next: ["下一页 →", "Next →"],
  mark: ["＋ 书签", "+ Mark"], translate: ["划词翻译", "Translate"],
  tagline: ["字里行间，自有天地", "A little room to read"],
  empty: ["从本机导入 EPUB、PDF、TXT 或 Markdown。", "Import a local EPUB, PDF, TXT or Markdown file."],
  importNote: ["导入会在本机书库创建独立副本。", "Import creates an independent copy in the local library."],
  copyNote: ["成功后，修改、移动或删除原文件均不影响书库副本。", "After import, editing, moving or deleting the original leaves the library copy intact."],
  copyDirectory: ["副本保存目录", "Library copy directory"],
  chooseFile: ["选择文件", "Choose file"],
  loading: ["正在打开…", "Opening…"], importing: ["正在导入…", "Importing…"],
  operation_failed: ["操作未完成，请重试。", "The operation could not be completed."],
  missing: ["文件或书籍不可用。", "The file or book is unavailable."],
  pdfSetup: ["首次阅读 PDF 需要下载 PDF.js 渲染器，之后可离线阅读。", "PDF.js is downloaded once, then PDF reading works offline."],
  pdfInstall: ["下载渲染器", "Download renderer"], pdfLoading: ["正在渲染 PDF…", "Rendering PDF…"],
  pdfError: ["无法渲染此 PDF。", "This PDF could not be rendered."],
  page: ["页", "Page"], part: ["节", "Section"],
  archive: ["归档", "Archive"], restore: ["恢复", "Restore"], delete: ["删除", "Delete"],
  archiveAsk: ["归档会保留书签和阅读进度。", "Archiving keeps bookmarks and reading progress."],
  restoreAsk: ["恢复后会在书架显示此书。", "Restoring returns this book to the shelf."],
  deleteAsk: ["删除书库副本及阅读记录，原文件保留。", "Delete the library copy and reading data. The original file is kept."],
  cancel: ["取消", "Cancel"], marked: ["已添加书签", "Bookmark added"],
  noMarks: ["还没有 Web 阅读书签。", "No Web reading bookmarks yet."],
  globalTarget: ["全局翻译目标语言", "Default translation target"],
  bookTarget: ["仅本书的目标语言", "Target for this book"],
  system: ["跟随系统", "Follow system"], inherit: ["沿用全局默认", "Use global default"],
  source: ["原文语言", "Source language"], auto: ["自动识别", "Auto detect"],
  target: ["目标语言", "Target language"], saved: ["已保存", "Saved"],
  translationNote: ["翻译在本机处理。首次使用语种组合时会下载模型，可能需要几分钟。", "Translation runs on this device. The first use of a language pair downloads models and may take a few minutes."],
  translating: ["正在准备模型或翻译…", "Preparing models or translating…"],
  onlineTranslating: ["正在翻译…", "Translating…"],
  translationEngine: ["翻译引擎", "Translation engine"],
  local: ["本地 · Argos", "On-device · Argos"],
  youdao: ["有道网页翻译", "Youdao Web"],
  google: ["Google 网页翻译", "Google Translate Web"],
  automaticTranslation: ["松开鼠标后自动翻译选区", "Translate automatically when selection ends"],
  onlineTranslationNote: ["使用在线引擎时，选中文字和语种会发送给所选服务。", "Online translation sends the selected text and language codes to the chosen service."],
  web_translation_failed: ["网页翻译暂时不可用，请重试或切换引擎。", "Web translation is unavailable. Try again or switch engines."],
  youdao_language_pair: ["有道网页支持简体中文与英语、日语、韩语、法语、俄语、西班牙语互译。", "Youdao Web supports Simplified Chinese paired with English, Japanese, Korean, French, Russian, or Spanish."],
  translation_provider_changed: ["翻译引擎已更改，请刷新页面。", "The translation engine changed. Reload this page."],
  image: ["书内图片", "Book image"], fit: ["适应窗口", "Fit"],
  zoomIn: ["放大", "Zoom in"], zoomOut: ["缩小", "Zoom out"],
  imageError: ["无法加载此图片。", "This image could not be loaded."],
  close: ["关闭", "Close"],
  restartRequired: ["阅读服务需要重启。请在终端按 Ctrl+C，再运行 modu --serve 并刷新页面。", "Restart the reader service with Ctrl+C, run modu --serve, then reload this page."],
  vocabulary: ["生词本", "Vocabulary"], saveWord: ["加入生词本", "Save word"],
  save: ["保存", "Save"],
  noWords: ["还没有生词。划选单词并翻译后可添加。", "No saved words yet. Select and translate a word to add it."],
  filterWords: ["查找生词", "Find a word"], meaning: ["译文", "Meaning"],
  speak: ["原文发音", "Pronounce"], onlineSpeak: ["有道发音", "Youdao audio"],
  onlineSpeechNote: ["点击后将原文发送给有道获取发音。", "Sends the original text to Youdao when clicked."],
  speech_failed: ["发音不可用，请重试。", "Audio is unavailable. Please try again."],
  speechUnavailable: ["浏览器没有此语言的本地语音。英文可尝试有道发音。", "No local voice for this language. For English, try Youdao audio."],
  speech_too_long: ["发音最多支持 200 个字符。", "Pronunciation supports up to 200 characters."],
  removeWord: ["从生词本移除此词？", "Remove this word from Vocabulary?"],
  highlightUnavailable: ["此浏览器不支持正文生词标注，可从生词本查看。", "This browser cannot highlight vocabulary. Open Vocabulary to review saved words."],
  translationOptions: ["翻译选项", "Translation options"],
  phonetics: ["查询音标", "Look up IPA"], phonetics_failed: ["音标暂不可用，点击重试", "IPA unavailable. Retry"],
  noPhonetics: ["暂无音标", "IPA unavailable"],
  uk: ["英", "UK"], us: ["美", "US"],
  ukSpeak: ["英式发音 · 有道", "British pronunciation · Youdao"],
  usSpeak: ["美式发音 · 有道", "American pronunciation · Youdao"],
  phoneticsNote: ["音标与在线发音由有道提供", "IPA and online audio by Youdao"],
  phoneticsLookupNote: ["将此单词发送给有道查询音标", "Send this word to Youdao to look up IPA"],
  savedWord: ["已收藏", "Saved"],
  unsaveWord: ["取消收藏", "Remove word"],
  manageWord: ["管理生词", "Edit saved word"],
  too_long: ["请选择不超过 600 个字符的文字。", "Select up to 600 characters."],
  unsupported_language: ["暂不支持这组语言。请在设置中选择其他目标语言。", "This language pair is unavailable. Choose another target in Settings."],
  dependencies: ["请安装 MODU 的 translation 扩展。", "Install MODU with its translation extra."],
  model_download: ["模型下载失败。请检查网络后重试。", "Model download failed. Check your connection and try again."],
  translation_failed: ["翻译未完成，请尝试更短的选区。", "Translation failed. Try a shorter selection."],
  invalid_book: ["这本书已不可用。", "This book is unavailable."],
};
let locale = 0;
let shelfData;
let archived = false;
let book;
let theme;
let spot = {index: 0, scroll: 0};
let pendingFrame;
let frameObserver;
let selection = "";
let selectionTimer;
let translationRequest;
let words = [];
let wordRanges = [];
let wordDocument;
let audioPlayer;
let audioUrl;
let speechRequest;
let speechControl;
let previewDocument;
const phoneticCache = new Map();
const boundImages = new WeakSet();
let toastTimer;
let saveTimer;
let bookGeneration = 0;
let pdfGeneration = 0;
let pdfDocument;
let pdfEngine;
let pdfTask;
let pager;
let flowRequest;
let pendingSearch;
let layoutAnchor;
let searchGeneration = 0;
const pageHistory = [];
let sidebarOpen = innerWidth > 720;

function label(key) {
  return (strings[key] || strings.operation_failed)[locale];
}

function element(tag, text, classes) {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  if (classes) node.className = classes;
  return node;
}

function button(text, handler) {
  const node = element("button", text);
  node.type = "button";
  node.addEventListener("click", handler);
  return node;
}

function icon(name) {
  const paths = {
    speaker: ["M11 5 6 9H3v6h3l5 4V5Z", "M15 8a6 6 0 0 1 0 8", "M18 5a10 10 0 0 1 0 14"],
    close: ["m6 6 12 12", "M18 6 6 18"],
    bookmark: ["M6 4h12v17l-6-4-6 4V4Z"],
    check: ["m5 12 4 4L19 6"],
    chevron: ["m9 5 7 7-7 7"],
  };
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  for (const [key, value] of Object.entries({viewBox:"0 0 24 24", width:"18", height:"18", fill:"none", stroke:"currentColor", "stroke-width":"1.7", "stroke-linecap":"round", "stroke-linejoin":"round", "aria-hidden":"true"})) svg.setAttribute(key, value);
  for (const d of paths[name]) {
    const path = document.createElementNS(svg.namespaceURI, "path");
    path.setAttribute("d", d);
    svg.append(path);
  }
  return svg;
}

function iconButton(name, title, handler) {
  const control = button("", handler);
  control.className = "icon-button";
  control.setAttribute("aria-label", title);
  control.title = title;
  control.append(icon(name));
  return control;
}

async function api(path, data, extra = {}) {
  const options = data === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data),
  };
  const response = await fetch(endpoint(path), {...options, ...extra});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error);
  return value;
}

function toast(message) {
  clearTimeout(toastTimer);
  $("toast").textContent = message;
  $("toast").hidden = false;
  toastTimer = setTimeout(() => $("toast").hidden = true, 3500);
}

function report(error) {
  toast(label(error.message));
}

function bookPath(item = book) {
  return "book/" + item.id;
}

function setLabels() {
  root.lang = locale ? "en" : "zh";
  for (const node of document.querySelectorAll("[data-label]")) node.textContent = label(node.dataset.label);
  $("tagline").textContent = label("tagline");
  frame.title = label("contents");
  $("selection-close").replaceChildren(icon("close"));
  $("selection-close").setAttribute("aria-label", label("close"));
  $("selection-close").title = label("close");
}

function setTheme(name, persist = true) {
  theme = name;
  const palette = shelfData.themes[name];
  ["bg", "fg", "accent", "muted", "panel"].forEach((key, i) => root.style.setProperty("--" + key, palette.colors[i]));
  root.style.colorScheme = palette.light ? "light" : "dark";
  themeFrame();
  if (persist) api("api/theme", {theme}).catch(report);
}

function themeFrame() {
  const body = frame.contentDocument?.documentElement;
  if (!body) return;
  const palette = shelfData.themes[theme];
  body.style.setProperty("--modu-bg", palette.colors[0]);
  body.style.setProperty("--modu-fg", palette.colors[1]);
  body.style.setProperty("--modu-scheme", palette.light ? "light" : "dark");
  body.style.setProperty("--modu-accent", palette.colors[2]);
}

function syncSidebar() {
  $("sidebar").hidden = !sidebarOpen;
  $("toc-button").setAttribute("aria-expanded", String(sidebarOpen));
}

function showDialog(title, children, mode = "") {
  clearSelection();
  dialog.className = mode;
  $("dialog-title").textContent = title;
  $("dialog-body").replaceChildren(...children);
  if (!dialog.open) dialog.showModal();
}

function confirmAction(title, question, handler) {
  const cancel = button(label("cancel"), () => dialog.close());
  const confirm = button(title, async () => {
    dialog.close();
    try { await handler(); } catch (error) { report(error); }
  });
  const actions = element("div", null, "dialog-actions");
  actions.append(cancel, confirm);
  showDialog(title, [element("p", question), actions]);
  cancel.focus();
}

function renderShelf() {
  $("archive-toggle").textContent = label(archived ? "shelf" : "archived");
  const rows = shelfData.books.filter(item => Boolean(item.archived) === archived);
  $("shelf-caption").textContent = label("importNote");
  $("books").replaceChildren();
  if (!rows.length) $("books").append(element("p", label("empty"), "muted"));
  for (const item of rows) {
    const row = element("div", null, "book-row");
    const open = button(item.title, () => openBook(item.id));
    open.append(element("small", [item.author, item.format].filter(Boolean).join(" · ")));
    const action = archived ? "restore" : "archive";
    row.append(open, button(label(action), () => confirmAction(label(action), label(action + "Ask"), async () => {
      await api(bookPath(item) + "/archive", {archived: !archived});
      await loadShelf();
    })), button(label("delete"), () => confirmAction(label("delete"), label("deleteAsk"), async () => {
      await api(bookPath(item) + "/delete", {});
      await loadShelf();
    })));
    $("books").append(row);
  }
}

async function loadShelf() {
  shelfData = await api("api/shelf");
  locale = shelfData.language === "en" ? 1 : 0;
  setLabels();
  setTheme(shelfData.theme, false);
  renderShelf();
  if (shelfData.serverVersion) words = await api("api/vocabulary");
  else toast(label("restartRequired"));
}

function savePosition() {
  clearTimeout(saveTimer);
  if (!book || !isReady()) return;
  const item = book;
  const data = {...spot};
  fetch(endpoint(bookPath(item) + "/position"), {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data), keepalive: true,
  }).catch(() => {});
}

function isReady() {
  return Boolean(book && pager && !pendingFrame);
}

function rememberPosition() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(savePosition, 300);
}

function resetReader() {
  savePosition();
  clearInterval(frameObserver);
  bookGeneration++;
  pdfGeneration++;
  book = undefined;
  pendingFrame = undefined;
  pendingSearch = undefined;
  layoutAnchor = undefined;
  flowRequest = undefined;
  searchGeneration++;
  clearSelection();
  wordRanges = [];
  wordDocument = undefined;
  frame.hidden = true;
  frame.removeAttribute("src");
  pdfView.hidden = true;
  pdfView.replaceChildren();
  pdfTask?.destroy().catch(() => {});
  pdfTask = pdfDocument = undefined;
  clearPager();
  pageHistory.length = 0;
  return bookGeneration;
}

function backToShelf() {
  resetReader();
  $("reader").hidden = true;
  $("shelf").hidden = false;
  loadShelf().catch(report);
}

function readerState(message, action) {
  $("reader-state").replaceChildren(element("p", message));
  if (action) $("reader-state").append(action);
  $("reader-state").hidden = false;
}

async function openBook(id) {
  const generation = resetReader();
  $("shelf").hidden = true;
  $("reader").hidden = false;
  $("toc").replaceChildren();
  $("progress").textContent = "";
  $("book-title").textContent = "";
  syncSidebar();
  readerState(label("loading"));
  try {
    const data = await api("book/" + id);
    if (generation !== bookGeneration) return;
    book = data;
    $("book-title").textContent = book.title;
    const position = book.position || {index: 0, scroll: 0};
    if (book.format === "pdf") {
      if (!book.pdfReady) {
        readerState(label("pdfSetup"), button(label("pdfInstall"), async () => {
          readerState(label("loading"));
          try {
            await api("api/pdf-install", {});
            if (generation === bookGeneration) await openBook(id);
          } catch (error) {
            if (generation === bookGeneration) {
              report(error);
              await openBook(id);
            }
          }
        }));
      } else {
        await loadPdf(generation, position);
      }
    } else {
      renderToc();
      jump(position);
    }
  } catch (error) {
    if (generation === bookGeneration) readerState(label(error.message));
  }
}

function total() {
  return book?.format === "pdf" ? pdfDocument?.numPages || 0 : book?.chapters.length || 0;
}

function boundedSpot(value) {
  const position = {
    index: Number.isInteger(value.index) ? Math.max(0, Math.min(total() - 1, value.index)) : 0,
    scroll: Number.isFinite(value.scroll) ? Math.max(0, Math.min(1, value.scroll)) : 0,
  };
  if (Number.isFinite(value.offset)) position.offset = Math.max(0, Math.min(1, value.offset));
  return position;
}

function renderToc() {
  const rows = book.format === "pdf"
    ? Array.from({length: total()}, (_, index) => ({index, label: label("page") + " " + (index + 1)}))
    : book.toc.map(chapter => ({...chapter, index: book.chapters.findIndex(item => item.name === chapter.name)}));
  $("toc").replaceChildren();
  for (const entry of rows) {
    if (entry.index < 0) continue;
    const node = button(entry.label, () => {
      jump({index: entry.index, scroll: 0}, entry.fragment || "");
      if (innerWidth <= 720) { sidebarOpen = false; syncSidebar(); }
    });
    node.dataset.index = entry.index;
    node.dataset.fragment = entry.fragment || "";
    $("toc").append(node);
  }
}

function updateProgress() {
  const count = total();
  if (!count) return;
  const unit = label(book.format === "pdf" ? "page" : "part");
  const percent = (spot.index + (book.format === "pdf" ? 1 : spot.scroll)) / count;
  $("progress").textContent = (locale ? unit + " " : "") + (spot.index + 1) + " / " + count
    + (locale ? "" : " " + unit) + " · " + Math.round(percent * 100) + "%";
  $("previous").disabled = !pager || (spot.index === 0 && pager.top <= 1);
  const finalSection = flowMode() ? Number(sections().at(-1)?.dataset.moduSection) === count - 1 : spot.index === count - 1;
  $("next").disabled = !pager || (finalSection && pager.end >= pager.extent - 1);
  let current;
  const view = frame.contentDocument?.scrollingElement;
  for (const entry of $("toc").children) {
    entry.removeAttribute("aria-current");
    if (Number(entry.dataset.index) !== spot.index) continue;
    const target = view && entry.dataset.fragment && frameAnchor(frame.contentDocument, entry.dataset.fragment);
    if (!current || !target || target.getBoundingClientRect().top < 55) current = entry;
  }
  current?.setAttribute("aria-current", "location");
}

function clearPager() {
  pager?.dispose();
  pager = undefined;
}

function updatePosition() {
  if (!pager || pager.layout !== pager.geometry) return;
  if (pager.releaseOnScroll()) pageHistory.length = 0;
  Object.assign(spot, flowMode() ? flowLocation(pager.top) : pager.position);
  updateProgress();
  rememberPosition();
}

function jump(value, fragment = "", turning = false) {
  if (!book || !total()) return;
  if (flowMode()) return jumpFlow(value, fragment, turning);
  const sameSection = spot.index === value.index;
  if (!turning) pageHistory.length = 0;
  spot = boundedSpot(value);
  clearSelection();
  if (book.format === "pdf") {
    if (sameSection && pager) {
      pager.restore(spot, value.endRatio);
      updatePosition();
      return;
    }
    clearPager();
    updateProgress();
    renderPdf(value.endRatio).catch(() => {
      pdfView.hidden = true;
      readerState(label("pdfError"));
    });
    return;
  }
  const name = book.chapters[spot.index].name;
  const route = book.format === "epub" ? "epub/" + name.split("/").map(encodeURIComponent).join("/") : "text/" + spot.index;
  const url = endpoint(bookPath() + "/" + route);
  if (fragment) url.hash = encodeURIComponent(fragment);
  if (pager && frame.contentDocument && frame.contentWindow.location.pathname === url.pathname) {
    if (fragment) {
      frameAnchor(frame.contentDocument, fragment)?.scrollIntoView();
      pager.prepare();
    } else {
      pager.restore(spot, value.endRatio);
    }
    updatePosition();
    return;
  }
  clearPager();
  pendingFrame = {url: url.pathname, position: spot, fragment, endRatio: value.endRatio};
  clearInterval(frameObserver);
  frame.src = url;
  frame.hidden = false;
  $("reader-state").hidden = true;
  updateProgress();
}

function onFrameScroll() {
  if (!book || frame.hidden || pendingFrame) return;
  const doc = frame.contentDocument;
  if (!doc || currentFrameIndex() < 0) return;
  if (!selectionPreview.hidden) clearSelection();
  updatePosition();
}

function frameAnchor(doc, fragment) {
  return doc.getElementById(fragment) || doc.getElementsByName(fragment)[0];
}

function currentFrameIndex() {
  const flowPrefix = endpoint(bookPath() + "/flow/").pathname;
  if (frame.contentWindow.location.pathname.startsWith(flowPrefix)) return Number(frame.contentWindow.location.pathname.slice(flowPrefix.length));
  const part = book.format === "epub" ? "/epub/" : "/text/";
  const prefix = endpoint(bookPath() + part).pathname;
  const pathname = frame.contentWindow.location.pathname;
  if (!pathname.startsWith(prefix)) return -1;
  const name = decodeURIComponent(pathname.slice(prefix.length));
  return book.chapters.findIndex(item => item.name === name);
}

frame.addEventListener("load", () => {
  clearInterval(frameObserver);
  if (!book || frame.hidden) return;
  const doc = frame.contentDocument;
  if (!doc || !frame.contentWindow.location.pathname.startsWith(endpoint(bookPath() + "/").pathname)) return;
  themeFrame();
  applyReadingStyle();
  const contentWindow = frame.contentWindow;
  const index = currentFrameIndex();
  if (index >= 0) spot.index = index;
  const previous = pendingFrame;
  pendingFrame = undefined;
  clearPager();
  if (doc.scrollingElement) {
    pager = new ScreenPages(doc.scrollingElement, frame, doc.body);
    if (previous?.url === contentWindow.location.pathname && !previous.fragment) {
      if (flowMode()) pager.show(flowTop(previous.position));
      else pager.restore(previous.position, previous.endRatio);
    } else {
      if (previous?.fragment) frameAnchor(doc, previous.fragment)?.scrollIntoView();
      else if (!previous) pageHistory.length = 0;
      pager.prepare();
    }
  }
  restoreLayoutAnchor();
  doc.addEventListener("scroll", onFrameScroll, {passive: true});
  doc.addEventListener("keydown", keyboard);
  bindSelection(doc, doc, () => frame.getBoundingClientRect());
  bindVocabulary(doc);
  highlightWords();
  if (book.format === "epub") bindImages(doc);
  doc.addEventListener("click", event => {
    if (!flowMode()) return;
    const link = event.target.closest("a[href]");
    if (!link) return;
    const url = new URL(link.href);
    const prefix = endpoint(bookPath() + "/epub/").pathname;
    const index = url.pathname.startsWith(prefix) ? book.chapters.findIndex(chapter => chapter.name === decodeURIComponent(url.pathname.slice(prefix.length))) : spot.index;
    if (index < 0) return;
    event.preventDefault();
    jump({index, scroll: 0}, decodeURIComponent(url.hash.slice(1)));
  });
  onFrameScroll();
  if (flowMode()) ensureFlow().catch(report);
  applySearchHit();
  // WebKit can suppress events from the scriptless frame. Observe its DOM
  // from the reader window without granting the publication script access.
  frameObserver = setInterval(() => {
    if (frame.contentDocument !== doc || dialog.open) return;
    const selected = doc.getSelection();
    if (selected && selected.toString().trim() !== selection) {
      detectSelection(doc, () => frame.getBoundingClientRect());
    }
    if (pager && pager.position.offset !== spot.offset) onFrameScroll();
  }, 160);
});

async function loadPdf(generation, position) {
  readerState(label("pdfLoading"));
  pdfEngine ??= await import("./pdfjs/legacy/build/pdf.min.mjs");
  if (generation !== bookGeneration) return;
  pdfEngine.GlobalWorkerOptions.workerSrc = endpoint("pdfjs/legacy/build/pdf.worker.min.mjs").href;
  const asset = name => endpoint("pdfjs/" + name + "/").href;
  const task = pdfEngine.getDocument({
    url: endpoint(bookPath() + "/pdf").href,
    cMapUrl: asset("cmaps"), cMapPacked: true, standardFontDataUrl: asset("standard_fonts"),
    wasmUrl: asset("wasm"), iccUrl: asset("iccs"), enableXfa: false, isEvalSupported: false,
    maxImageSize: 20_000_000, canvasMaxAreaInBytes: 64_000_000,
  });
  pdfTask = task;
  try {
    const document = await task.promise;
    if (generation !== bookGeneration) return;
    pdfDocument = document;
    renderToc();
    spot = boundedSpot(position);
    await renderPdf();
  } catch (error) {
    if (generation === bookGeneration) readerState(label("pdfError"));
  }
}

async function renderPdf(endRatio) {
  const generation = ++pdfGeneration;
  const current = {...spot};
  const page = await pdfDocument.getPage(current.index + 1);
  if (generation !== pdfGeneration) return;
  const original = page.getViewport({scale: 1});
  const scale = Math.min(1100, Math.max(260, $("viewport").clientWidth - 32)) / original.width;
  const viewport = page.getViewport({scale});
  const pixels = Math.min(devicePixelRatio || 1, 2, Math.sqrt(12_000_000 / (viewport.width * viewport.height)));
  const wrap = element("div", null, "pdf-page");
  wrap.style.width = viewport.width + "px";
  wrap.style.height = viewport.height + "px";
  wrap.style.setProperty("--scale-factor", scale);
  wrap.style.setProperty("--total-scale-factor", scale);
  const canvas = element("canvas");
  canvas.width = Math.ceil(viewport.width * pixels);
  canvas.height = Math.ceil(viewport.height * pixels);
  canvas.style.width = viewport.width + "px";
  canvas.style.height = viewport.height + "px";
  const text = element("div", null, "textLayer");
  wrap.append(canvas, text);
  await page.render({canvas, viewport, transform: [pixels, 0, 0, pixels, 0, 0]}).promise;
  if (generation !== pdfGeneration) return;
  const layer = new pdfEngine.TextLayer({textContentSource: page.streamTextContent(), container: text, viewport});
  await layer.render();
  if (generation !== pdfGeneration) return;
  clearPager();
  pdfView.replaceChildren(wrap);
  pdfView.hidden = false;
  $("reader-state").hidden = true;
  pager = new ScreenPages(pdfView, pdfView, pdfView);
  pager.restore(current, endRatio);
  highlightWords();
  updatePosition();
  applySearchHit();
}

pdfView.addEventListener("scroll", () => {
  if (!selectionPreview.hidden) clearSelection();
  if (book?.format === "pdf" && !pdfView.hidden) updatePosition();
}, {passive: true});

async function navigate(delta) {
  if (!isReady()) return;
  if (flowMode() && delta > 0) {
    try { await ensureFlow(); } catch (error) { report(error); return; }
    if (!isReady()) return;
  }
  if (pager.resize(spot) || pager.releaseOnScroll()) pageHistory.length = 0;
  clearSelection();
  if (delta < 0) {
    const previous = pageHistory.pop();
    if (previous) jump(previous, "", true);
    else if (pager.top > 1) {
      pager.previous();
      updatePosition();
    } else if (spot.index > 0) jump({index: spot.index - 1, scroll: 1}, "", true);
    return;
  }
  if (pager.cut === undefined) pager.prepare();
  const next = pager.end;
  const moreHere = next < pager.extent - 1 && next > pager.top + 1;
  if (!moreHere && (flowMode() ? Number(sections().at(-1)?.dataset.moduSection) >= total() - 1 : spot.index >= total() - 1)) return;
  pageHistory.push(flowMode() ? {...spot, endLocation: flowLocation(next)} : {index: spot.index, ...pager.position, endRatio: next / pager.extent});
  if (pageHistory.length > 512) pageHistory.shift();
  if (moreHere) {
    pager.show(next);
    updatePosition();
  } else {
    jump({index: spot.index + 1, scroll: 0}, "", true);
  }
}

function selectField(title, choices, value, onChange) {
  const field = element("label", title);
  const select = element("select");
  select.setAttribute("aria-label", title);
  for (const [key, name] of choices) {
    const option = element("option", name);
    option.value = key;
    select.append(option);
  }
  select.value = value || "";
  if (onChange) select.addEventListener("change", () => onChange(select).catch(report));
  field.append(select);
  return field;
}

async function settings() {
  try {
    if (!shelfData.serverVersion) return toast(label("restartRequired"));
    const item = book;
    const latest = await api("api/shelf");
    shelfData.translationOptions = latest.translationOptions;
    const preferences = translationOptions();
    const choices = Object.entries(shelfData.languages);
    const value = item ? (await api(bookPath(item))).translation : latest.translation;
    const notice = element("p", translationNotice(preferences.provider), "muted");
    const engine = selectField(label("translationEngine"),
      ["local", "youdao", "google"].map(key => [key, label(key)]), preferences.provider,
      async select => {
        await saveTranslationOption(select, {provider: select.value}, "value");
        notice.textContent = translationNotice(translationOptions().provider);
      });
    const automatic = element("input");
    automatic.type = "checkbox";
    automatic.checked = preferences.automatic;
    automatic.addEventListener("change", () => {
      saveTranslationOption(automatic, {automatic: automatic.checked}, "checked").catch(report);
    });
    const automaticField = element("label", null, "checkbox-field");
    automaticField.append(automatic, element("span", label("automaticTranslation")));
    const global = selectField(label("globalTarget"), [["", label("system") + " · " + (shelfData.languages[value.system_target] || value.system_target)], ...choices], value.global_target, async select => {
      const updated = await api("api/translation", {target: select.value});
      if (item && book === item) item.translation = (await api(bookPath(item))).translation;
      highlightWords();
      select.value = updated.global_target;
      toast(label("saved"));
    });
    shelfData.readingOptions = latest.readingOptions;
    const layoutTitle = element("h3", label("readingSettings"));
    const width = selectField(label("readWidth"), [64, 80, 96].map(value => [String(value), String(value) + " ch"]), String(readingOptions().read_width), async control => saveReadingOption(control, {read_width: Number(control.value)}));
    const spacing = selectField(label("spacing"), [["0", label("compact")], ["1", label("relaxed")], ["2", label("airy")]], String(readingOptions().spacing), async control => saveReadingOption(control, {spacing: Number(control.value)}));
    const chapterInput = element("input");
    chapterInput.type = "checkbox";
    chapterInput.checked = readingOptions().chapter_breaks;
    chapterInput.addEventListener("change", () => saveReadingOption(chapterInput, {chapter_breaks: chapterInput.checked}).catch(report));
    const chapterField = element("label", null, "checkbox-field");
    chapterField.append(chapterInput, element("span", label("chapterBreaks")));
    const nodes = [layoutTitle, width, spacing, chapterField];
    if (item?.format === "pdf") {
      for (const field of [width, spacing]) field.querySelector("select").disabled = true;
      chapterInput.disabled = true;
      nodes.push(element("p", label("fixedLayout"), "muted"));
    }
    nodes.push(element("h3", label("translationOptions")), engine, notice, automaticField, global);
    if (item) nodes.push(selectField(label("bookTarget"), [["", label("inherit")], ...choices], value.book_target, async select => {
      item.translation = await api(bookPath(item) + "/translation", {target: select.value});
      highlightWords();
      toast(label("saved"));
    }));
    showDialog(label("settings"), nodes);
  } catch (error) { report(error); }
}


function textNodes(surface) {
  const walker = surface.ownerDocument.createTreeWalker(surface, NodeFilter.SHOW_TEXT);
  const nodes = [];
  let node;
  while ((node = walker.nextNode())) if (!node.parentElement.closest("style,script,head,[hidden]")) nodes.push(node);
  return nodes;
}

function captureLayoutAnchor() {
  if (!book || book.format === "pdf" || !pager?.anchor) return;
  const {range, inset} = pager.anchor;
  const surface = range.startContainer.parentElement.closest("[data-modu-section]") || frame.contentDocument.body;
  let offset = 0;
  for (const node of textNodes(surface)) {
    if (node === range.startContainer) return {book: book.id, index: spot.index, offset: offset + range.startOffset, inset};
    offset += node.length;
  }
}

function restoreLayoutAnchor() {
  const saved = layoutAnchor;
  layoutAnchor = undefined;
  if (!saved || !pager || saved.book !== book?.id || saved.index !== spot.index) return;
  const surface = flowMode() ? sections().find(node => Number(node.dataset.moduSection) === spot.index) : frame.contentDocument.body;
  let offset = saved.offset;
  for (const node of textNodes(surface)) {
    if (offset <= node.length) {
      const range = node.ownerDocument.createRange();
      range.setStart(node, offset); range.collapse(true);
      const rect = range.getBoundingClientRect();
      pager.show(pager.top + rect.top - pager.viewport.top - saved.inset);
      return;
    }
    offset -= node.length;
  }
}

function readingOptions() {
  return shelfData?.readingOptions || {read_width: 80, spacing: 1, chapter_breaks: true};
}

function flowMode() {
  return book && book.format !== "pdf" && !readingOptions().chapter_breaks;
}

function sections() {
  return Array.from(frame.contentDocument?.querySelectorAll("body > [data-modu-section]") || []);
}

function sectionTop(node) {
  return node.getBoundingClientRect().top + pager.top;
}

function flowLocation(top) {
  const list = sections();
  const node = list.findLast(node => sectionTop(node) <= top + 1) || list[0];
  if (!node) return {...spot};
  const height = Math.max(1, node.getBoundingClientRect().height);
  const local = Math.max(0, top - sectionTop(node));
  return {index: Number(node.dataset.moduSection), offset: Math.min(1, local / height), scroll: Math.min(1, local / Math.max(1, height - pager.height))};
}

function flowTop(position) {
  const node = sections().find(node => Number(node.dataset.moduSection) === position.index);
  if (!node) return 0;
  const height = node.getBoundingClientRect().height;
  return sectionTop(node) + (Number.isFinite(position.offset) ? position.offset * height : position.scroll * Math.max(0, height - pager.height));
}

function applyReadingStyle() {
  const doc = frame.contentDocument;
  if (!doc?.head || !shelfData) return;
  let style = doc.getElementById("modu-reading-style");
  if (!style) { style = doc.createElement("style"); style.id = "modu-reading-style"; doc.head.append(style); }
  const prefs = readingOptions();
  const body = flowMode() ? ".modu-body" : "body";
  const gap = [0.35, 1, 1.6][prefs.spacing];
  style.textContent = `
    ${body} {display:flow-root!important;box-sizing:border-box!important;width:100%!important;max-width:${prefs.read_width}ch!important;margin-inline:auto!important;padding-inline:clamp(12px,3vw,28px)!important;overflow-wrap:break-word!important;color:var(--modu-fg)!important;background:transparent!important}
    ${body} p {margin-block:${gap}em!important}
    ${body} img, ${body} svg {max-width:100%!important;object-fit:contain}
    ${body} pre, ${body} table {max-width:100%;overflow-x:auto}
    ::highlight(modu-search) {background:#d4b477;color:#171717}
    [data-modu-section] {display:flow-root;min-height:1px}
    .modu-html {color:var(--modu-fg);background:transparent!important}
  `;
}

async function saveReadingOption(control, change) {
  control.disabled = true;
  const old = {...readingOptions()};
  const current = {...spot};
  const anchor = pager?.anchor;
  const portable = captureLayoutAnchor();
  try {
    shelfData.readingOptions = await api("api/reading-options", change);
    pageHistory.length = 0;
    if (book && book.format !== "pdf") {
      if (old.chapter_breaks !== readingOptions().chapter_breaks) {
        layoutAnchor = portable;
        clearPager();
        jump(current);
      } else {
        applyReadingStyle();
        if (anchor?.range.startContainer.isConnected && pager) {
          const rect = anchor.range.getBoundingClientRect();
          pager.show(pager.top + rect.top - pager.viewport.top - anchor.inset);
        } else if (pager) {
          flowMode() ? pager.show(flowTop(current)) : pager.restore(current);
        }
        updatePosition();
      }
    }
    toast(label("saved"));
  } finally {
    const key = Object.keys(change)[0];
    if (control.type === "checkbox") control.checked = readingOptions()[key];
    else control.value = String(readingOptions()[key]);
    control.disabled = false;
  }
}

function jumpFlow(value, fragment, turning) {
  if (!turning) pageHistory.length = 0;
  clearSelection();
  spot = boundedSpot(value);
  const node = sections().find(node => Number(node.dataset.moduSection) === spot.index);
  if (node && pager) {
    if (fragment) {
      const target = Array.from(node.querySelectorAll("[id], [name]")).find(child => child.id === fragment || child.getAttribute("name") === fragment);
      target?.scrollIntoView();
      pager.prepare();
    } else {
      pager.show(flowTop(spot), value.endLocation ? flowTop(value.endLocation) : undefined);
    }
    updatePosition();
    ensureFlow().catch(report);
    return;
  }
  clearPager();
  const url = endpoint(bookPath() + "/flow/" + spot.index);
  pendingFrame = {url: url.pathname, position: {...spot}, fragment};
  clearInterval(frameObserver);
  frame.src = url;
  frame.hidden = false;
  $("reader-state").hidden = true;
  updateProgress();
}

async function ensureFlow() {
  if (!flowMode() || !pager || pendingFrame) return;
  const doc = frame.contentDocument;
  if (flowRequest?.doc === doc) return flowRequest.promise;
  const active = {doc};
  active.promise = (async () => {
    const item = book;
    while (book === item && frame.contentDocument === doc && flowMode() && pager && pager.extent - pager.top < pager.height * 2 + 100) {
      const last = sections().at(-1);
      const index = Number(last.dataset.moduSection) + 1;
      if (index >= total()) return;
      const result = await api(bookPath(item) + "/section/" + index);
      if (book !== item || frame.contentDocument !== doc || !flowMode() || !pager) return;
      const top = pager.top;
      const template = doc.createElement("template");
      template.innerHTML = result.html;
      doc.body.insertBefore(template.content, pager.tail || null);
      // Decode images before measuring the next page to avoid late vertical shifts.
      const added = sections().at(-1);
      await Promise.allSettled(Array.from(added.querySelectorAll("img"), image => image.decode?.()));
      if (frame.contentDocument !== doc || !pager) return;
      pager.show(top);
      if (book.format === "epub") bindImages(doc);
      highlightWords();
    }
  })();
  flowRequest = active;
  try { await active.promise; } finally { if (flowRequest === active) flowRequest = undefined; }
}

function searchableText(surface) {
  const doc = surface.ownerDocument;
  const walker = doc.createTreeWalker(surface, NodeFilter.SHOW_TEXT);
  const mapping = [];
  let text = "", node, whitespace = false;
  while ((node = walker.nextNode())) {
    if (node.parentElement.closest("style,script,head,[hidden]")) continue;
    for (let offset = 0; offset < node.length; offset++) {
      const char = node.data[offset];
      if (/\s/u.test(char)) {
        if (text && !whitespace) { text += " "; mapping.push([node, offset]); }
        whitespace = true;
      } else {
        text += char; mapping.push([node, offset]); whitespace = false;
      }
    }
  }
  return {text: text.trimEnd(), mapping};
}

function literalMatches(text, query) {
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return text.matchAll(new RegExp(escaped, "giu"));
}

function applySearchHit() {
  if (!pendingSearch || !pager || pendingFrame || pendingSearch.book !== book?.id || spot.index !== pendingSearch.index) return;
  const hit = pendingSearch;
  pendingSearch = undefined;
  const surface = book.format === "pdf" ? pdfView.querySelector(".textLayer") : flowMode() ? sections().find(node => Number(node.dataset.moduSection) === hit.index) : frame.contentDocument.body;
  if (!surface) return;
  const {text, mapping} = searchableText(surface);
  const matches = Array.from(literalMatches(text, hit.query));
  const match = matches[hit.occurrence] || matches[0];
  if (!match || !mapping[match.index]) return;
  const range = surface.ownerDocument.createRange();
  const [first, start] = mapping[match.index];
  const [last, end] = mapping[match.index + match[0].length - 1];
  range.setStart(first, start); range.setEnd(last, end + 1);
  const rect = range.getBoundingClientRect();
  pager.show(pager.top + rect.top - pager.viewport.top - 20);
  const view = surface.ownerDocument.defaultView;
  if (view.CSS?.highlights && view.Highlight) view.CSS.highlights.set("modu-search", new view.Highlight(range));
  updatePosition();
}

function searchBook() {
  if (!book) return;
  const item = book;
  const input = element("input");
  input.type = "search"; input.maxLength = 200; input.placeholder = label("searchHint");
  input.setAttribute("aria-label", label("searchBook"));
  const info = element("p", "", "muted");
  info.setAttribute("role", "status");
  const results = element("div", null, "search-results");
  const run = async () => {
    const generation = ++searchGeneration;
    const query = input.value.replace(/\s+/gu, " ").trim();
    results.replaceChildren();
    if (!query) { info.textContent = ""; return; }
    info.textContent = label("searching");
    try {
      let data;
      if (item.format === "pdf") {
        if (!pdfDocument) throw Error("pdfError");
        data = {results: [], more: false};
        const pdf = pdfDocument;
        for (let index = 0; index < pdf.numPages; index++) {
          if (generation !== searchGeneration || book !== item || !dialog.open) return;
          const page = await pdf.getPage(index + 1);
          const content = await page.getTextContent();
          const text = content.items.map(item => item.str || "").join("").replace(/\s+/gu, " ").trim();
          let occurrence = 0;
          for (const match of literalMatches(text, query)) {
            data.results.push({index, occurrence: occurrence++, snippet: text.slice(Math.max(0, match.index - 45), match.index + query.length + 75)});
            if (data.results.length > 200) { data.more = true; break; }
          }
          if (data.more) { data.results.length = 200; break; }
        }
      } else data = await api(bookPath(item) + "/search", {query});
      if (generation !== searchGeneration || book !== item || !dialog.open || input.value.replace(/\s+/gu, " ").trim() !== query) return;
      info.textContent = data.results.length ? data.more ? label("searchMore") : `${data.results.length} ${label("searchResults")}` : label("noResults");
      for (const hit of data.results) {
        const row = button("", () => {
          dialog.close();
          pendingSearch = {...hit, query, book: item.id};
          jump({index: hit.index, scroll: 0});
          applySearchHit();
        });
        row.append(element("small", item.format === "pdf" ? `${label("page")} ${hit.index + 1}` : item.chapters[hit.index].label), element("span", hit.snippet));
        results.append(row);
      }
    } catch (error) { if (generation === searchGeneration) info.textContent = label(error.message); }
  };
  input.addEventListener("input", () => { searchGeneration++; results.replaceChildren(); info.textContent = ""; });
  input.addEventListener("keydown", event => { if (event.key === "Enter") { event.preventDefault(); run(); } });
  showDialog(label("searchBook"), [input, button(label("search"), run), info, results]);
  input.focus();
}

function translationOptions() {
  return shelfData?.translationOptions || {provider: "local", automatic: false};
}

async function saveTranslationOption(control, change, property) {
  const key = Object.keys(change)[0];
  control.disabled = true;
  try {
    const updated = await api("api/translation-options", change);
    shelfData.translationOptions = {...translationOptions(), [key]: updated[key]};
    toast(label("saved"));
  } finally {
    control[property] = translationOptions()[key];
    control.disabled = false;
  }
}

function translationNotice(provider) {
  return label(provider === "local" ? "translationNote" : "onlineTranslationNote");
}

function translating(provider) {
  return label(provider === "local" ? "translating" : "onlineTranslating");
}

function initialSource(item) {
  const language = item.sourceLanguage?.replaceAll("_", "-").toLowerCase();
  const primary = language?.split("-")[0];
  if (primary === "zh") return /(?:^|-)(?:hant|tw|hk|mo)(?:-|$)/.test(language) ? "zh-Hant" : "zh-Hans";
  return primary in shelfData.languages ? primary : "";
}

function clearSelection() {
  clearTimeout(selectionTimer);
  translationRequest?.abort();
  translationRequest = undefined;
  selection = "";
  selectionPreview.hidden = $("selection").hidden = true;
  previewDocument = undefined;
  stopSpeech();
}

function readingSelection(doc) {
  if (!book || dialog.open || (doc !== document && (frame.hidden || frame.contentDocument !== doc))) return;
  const range = doc.getSelection();
  if (!range?.rangeCount || range.isCollapsed) return;
  if (doc === document && (pdfView.hidden || !pdfView.contains(range.anchorNode) || !pdfView.contains(range.focusNode))) return;
  return range;
}

function placeSelection(node, range, box) {
  if (node === selectionPreview) previewDocument = range.anchorNode?.ownerDocument;
  const rect = range.getRangeAt(0).getBoundingClientRect();
  const left = box.left + rect.left;
  const below = box.top + rect.bottom + 7;
  const above = box.top + rect.top - node.offsetHeight - 7;
  const top = below + node.offsetHeight <= innerHeight - 8 ? below : above;
  node.style.left = Math.max(8, Math.min(innerWidth - node.offsetWidth - 8, left)) + "px";
  node.style.top = Math.max(8, Math.min(innerHeight - node.offsetHeight - 8, top)) + "px";
}

function detectSelection(doc, getBox) {
  if (dialog.open || (doc === document && book?.format !== "pdf")) return;
  const range = readingSelection(doc);
  const next = range?.toString().trim() || "";
  if (next !== selection && !selectionPreview.hidden) clearSelection();
  selection = next;
  $("selection").hidden = !selection || translationOptions().automatic;
  if (!$("selection").hidden) placeSelection($("selection"), range, getBox());
}

function bindSelection(doc, surface, getBox) {
  let pointer;
  doc.addEventListener("selectionchange", () => detectSelection(doc, getBox));
  surface.addEventListener("pointerdown", event => {
    if (event.isPrimary && event.button === 0) {
      clearSelection();
      pointer = event.pointerId;
    }
  });
  doc.addEventListener("pointercancel", event => {
    if (event.pointerId === pointer) pointer = undefined;
  });
  doc.addEventListener("pointerup", event => {
    if (event.pointerId !== pointer) return;
    pointer = undefined;
    if (translationOptions().automatic) {
      selectionTimer = setTimeout(() => previewTranslation(doc, getBox), 220);
    }
  });
}

async function previewTranslation(doc, getBox) {
  const item = book;
  const range = readingSelection(doc);
  const text = range?.toString().trim();
  if (!text || !translationOptions().automatic) return;
  if (Array.from(text).length > 600) return toast(label("too_long"));
  selection = text;
  const cached = savedWord(text);
  if (cached) return showSavedWord(cached, range.getRangeAt(0), doc, getBox());
  const {provider} = translationOptions();
  const request = new AbortController();
  translationRequest = request;
  $("selection-engine").textContent = text;
  $("selection-engine").classList.toggle("is-passage", text.length > 80);
  $("selection-source").textContent = label("translationOptions");
  $("selection-source").onclick = () => selectionDialog(false);
  const output = $("selection-result");
  output.textContent = translating(provider);
  $("selection-pronunciation").replaceChildren(...speechButtons(text, initialSource(item)));
  $("selection-actions").replaceChildren(element("span", label(provider), "lookup-provider"));
  selectionPreview.hidden = false;
  placeSelection(selectionPreview, range, getBox());
  try {
    const result = await api(bookPath(item) + "/translate", {text, source: initialSource(item), provider}, {signal: request.signal});
    if (!request.signal.aborted) {
      output.textContent = result.text;
      $("selection-pronunciation").replaceChildren(...speechButtons(text, result.source));
      $("selection-actions").replaceChildren(...wordButtons(text, result));
      if (!$("selection-actions").childElementCount) $("selection-actions").append(element("span", label(provider), "lookup-provider"));
    }
  } catch (error) {
    if (!request.signal.aborted) output.textContent = label(error.message);
  } finally {
    if (translationRequest === request) {
      translationRequest = undefined;
      const current = readingSelection(doc);
      if (current?.toString().trim() === text) placeSelection(selectionPreview, current, getBox());
      else clearSelection();
    }
  }
}

async function selectionDialog(start = true) {
  const text = selection;
  const item = book;
  $("selection").hidden = true;
  if (!item || !text) return;
  if (Array.from(text).length > 600) return toast(label("too_long"));
  if (!shelfData.serverVersion) return toast(label("restartRequired"));
  try {
    const pref = (await api(bookPath(item))).translation;
    if (book !== item) return;
    const {provider} = translationOptions();
    const options = Object.entries(shelfData.languages);
    const source = selectField(label("source"), [["", label("auto")], ...options], initialSource(item));
    const description = element("p", label("target") + " · " + (shelfData.languages[pref.target] || pref.target));
    const output = element("div", "", "translation-result lookup-meaning");
    output.hidden = true;
    output.setAttribute("aria-live", "polite");
    const actions = element("div", null, "word-actions");
    const pronunciation = element("div");
    pronunciation.append(...speechButtons(text, initialSource(item)));
    const localSpeech = element("div");
    localSpeech.append(...speechButtons(text, initialSource(item), true));
    const go = button(label("translate"), async () => {
      go.disabled = true;
      output.hidden = false;
      output.textContent = translating(provider);
      try {
        const result = await api(bookPath(item) + "/translate", {text, source: source.querySelector("select").value, provider});
        output.textContent = result.text;
        pronunciation.replaceChildren(...speechButtons(text, result.source));
        localSpeech.replaceChildren(...speechButtons(text, result.source, true));
        actions.replaceChildren(...wordButtons(text, result));
      } catch (error) { output.textContent = label(error.message); }
      finally { go.disabled = false; }
    });
    const details = element("details", null, "lookup-options");
    details.open = !start;
    details.append(element("summary", label("translationOptions")), source, description,
      element("p", translationNotice(provider), "muted"), localSpeech, go);
    const isWord = text.length <= 80 && !/\s/.test(text);
    const nodes = [pronunciation, output, actions, details];
    if (!isWord) nodes.unshift(element("p", text, "selected-original"));
    showDialog(isWord ? text : label("translate"), nodes, "lookup-dialog");
    const cached = savedWord(text);
    if (cached) {
      output.hidden = false;
      output.textContent = cached.translation;
      pronunciation.replaceChildren(...speechButtons(text, cached.source));
      actions.replaceChildren(...wordButtons(text, {text: cached.translation, source: cached.source, target: cached.target}));
    } else if (start) go.click();
  } catch (error) { report(error); }
}

function bindImages(doc) {
  const prefix = endpoint(bookPath() + "/epub/");
  function imageSource(image) {
    const source = image.currentSrc || image.getAttribute("src")
      || image.getAttribute("href") || image.getAttribute("xlink:href");
    if (!source) return;
    const url = new URL(source, doc.URL);
    if (url.origin === prefix.origin && url.pathname.startsWith(prefix.pathname)) return url.href;
  }
  for (const image of doc.querySelectorAll("img, svg image")) {
    if (boundImages.has(image) || !imageSource(image)) continue;
    boundImages.add(image);
    image.style.cursor = "zoom-in";
    if (!image.closest("a")) {
      image.setAttribute("tabindex", "0");
      image.setAttribute("role", "button");
      image.setAttribute("aria-label", label("zoomIn") + " · " + (image.getAttribute("alt") || label("image")));
    }
    function open(event) {
      const url = imageSource(image);
      if (!url || dialog.open || frame.contentDocument !== doc) return;
      event.preventDefault();
      showImage(url, image.getAttribute("alt") || label("image"));
    }
    image.addEventListener("click", event => {
      if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) open(event);
    });
    image.addEventListener("keydown", event => {
      if (event.key === "Enter") open(event);
    });
  }
}

function stopSpeech() {
  if (speechControl) {
    speechControl.classList.remove("is-loading", "is-playing");
    speechControl.setAttribute("aria-pressed", "false");
    speechControl.setAttribute("aria-busy", "false");
    speechControl = undefined;
  }
  speechRequest?.abort();
  speechRequest = undefined;
  window.speechSynthesis?.cancel();
  audioPlayer?.pause();
  audioPlayer = undefined;
  if (audioUrl) URL.revokeObjectURL(audioUrl);
  audioUrl = undefined;
}

function speechButtons(text, source, localOnly = false) {
  const row = element("div", null, "pronunciation-row");
  const english = source === "en" && !localOnly;
  const isWord = /^[a-z]+(?:['’\-][a-z]+)*$/i.test(text.trim()) && text.length <= 80;
  function onlineButton(accent, title) {
    const control = iconButton("speaker", title, async () => {
      if (speechControl === control) return stopSpeech();
      stopSpeech();
      const request = new AbortController();
      speechRequest = request;
      speechControl = control;
      control.classList.add("is-loading");
      control.setAttribute("aria-busy", "true");
      try {
        const response = await fetch(endpoint("api/pronounce"), {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({text, accent}), signal: request.signal,
        });
        if (!response.ok) throw new Error((await response.json()).error);
        const blob = await response.blob();
        if (request.signal.aborted) return;
        audioUrl = URL.createObjectURL(blob);
        audioPlayer = new Audio(audioUrl);
        audioPlayer.onended = () => { if (speechControl === control) stopSpeech(); };
        audioPlayer.onerror = () => { if (speechControl === control) { stopSpeech(); toast(label("speech_failed")); } };
        await audioPlayer.play();
        if (request.signal.aborted) return;
        control.classList.remove("is-loading");
        control.classList.add("is-playing");
        control.setAttribute("aria-busy", "false");
        control.setAttribute("aria-pressed", "true");
      } catch (error) {
        if (!request.signal.aborted) {
          stopSpeech();
          toast(label(error.message === "speech_too_long" ? error.message : "speech_failed"));
        }
      }
    });
    control.setAttribute("aria-pressed", "false");
    return control;
  }
  if (english && isWord) {
    const phones = {};
    for (const accent of ["uk", "us"]) {
      const group = element("div", null, "pronunciation-group");
      const phone = element("span", "", "ipa");
      phones[accent] = phone;
      group.append(element("span", label(accent), "accent-label"), phone,
        onlineButton(accent, label(accent + "Speak")));
      row.append(group);
    }
    const lookup = button(label("phonetics"), () => load(true));
    lookup.className = "text-button phonetics-lookup";
    lookup.title = label("phoneticsLookupNote");
    row.append(lookup);
    row.title = label("phoneticsNote");
    async function load(remote) {
      lookup.disabled = true;
      const key = wordKey(text);
      const cacheKey = key + ":" + remote;
      try {
        if (!phoneticCache.has(cacheKey)) {
          if (phoneticCache.size > 256) phoneticCache.clear();
          phoneticCache.set(cacheKey, api("api/phonetics", {word: key, lookup: remote}));
        }
        const result = await phoneticCache.get(cacheKey);
        if (Object.keys(result).length) phoneticCache.set(key + ":false", Promise.resolve(result));
        for (const accent of ["uk", "us"]) phones[accent].textContent = result[accent] ? "/" + result[accent] + "/" : "";
        lookup.hidden = Boolean(result.uk || result.us);
        lookup.textContent = label(remote ? "noPhonetics" : "phonetics");
      } catch {
        phoneticCache.delete(cacheKey);
        lookup.textContent = label("phonetics_failed");
      } finally { lookup.disabled = false; }
    }
    load(translationOptions().provider !== "local");
    return [row];
  }
  if (english) {
    row.append(element("span", label("speak"), "muted"), onlineButton("us", label("onlineSpeak")));
    return [row];
  }
  const local = iconButton("speaker", label("speak"), () => {
    if (speechControl === local) return stopSpeech();
    stopSpeech();
    if (Array.from(text).length > 200) return toast(label("speech_too_long"));
    const primary = (source || "en").split("-")[0];
    const voice = window.speechSynthesis?.getVoices().find(voice =>
      voice.localService && voice.lang.toLowerCase().split(/[-_]/)[0] === primary);
    if (!voice) return toast(label("speechUnavailable"));
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.voice = voice;
    utterance.lang = voice.lang;
    utterance.rate = 0.85;
    speechControl = local;
    local.classList.add("is-playing");
    local.setAttribute("aria-pressed", "true");
    utterance.onend = () => { if (speechControl === local) stopSpeech(); };
    utterance.onerror = event => {
      if (speechControl === local) stopSpeech();
      if (!["interrupted", "canceled"].includes(event.error)) toast(label("speech_failed"));
    };
    window.speechSynthesis.speak(utterance);
  });
  window.speechSynthesis?.getVoices();
  row.append(element("span", label("speak"), "muted"), local);
  return [row];
}

function wordKey(text) {
  return text.trim().normalize("NFC").replaceAll("’", "'").toLowerCase();
}

function activeWords() {
  const source = book && initialSource(book);
  return words.filter(word => (!source || word.source === source) && word.target === book?.translation.target);
}

function savedWord(text) {
  const key = wordKey(text);
  return activeWords().find(word => word.word_key === key);
}

function wordButtons(text, result) {
  if (Array.from(text).length > 80 || !/^\p{L}[\p{L}\p{M}]*(?:['’\-][\p{L}\p{M}]+)*$/u.test(text.trim())) return [];
  const currentEntry = () => words.find(word => word.word_key === wordKey(text)
    && word.source === result.source && word.target === result.target);
  const save = button(label("saveWord"), async () => {
    save.disabled = true;
    try {
      words = await api("api/vocabulary", {
        word: text, source: result.source, target: result.target,
        translation: result.text, remove: Boolean(currentEntry()),
      });
      highlightWords();
      render();
      if (save.parentElement === $("selection-actions")) {
        const entry = currentEntry();
        $("selection-source").textContent = label(entry ? "manageWord" : "translationOptions");
        $("selection-source").onclick = entry ? () => editWord(entry) : () => selectionDialog(false);
      }
    } catch (error) { report(error); }
    finally { save.disabled = false; }
  });
  save.className = "save-word";
  function render() {
    const saved = Boolean(currentEntry());
    save.replaceChildren(icon(saved ? "check" : "bookmark"), element("span", label(saved ? "savedWord" : "saveWord")));
    save.setAttribute("aria-pressed", String(saved));
    save.setAttribute("aria-label", label(saved ? "unsaveWord" : "saveWord"));
    save.title = label(saved ? "unsaveWord" : "saveWord");
  }
  render();
  return [save];
}

function highlightWords() {
  const doc = book?.format === "pdf" ? document : frame.contentDocument;
  const surface = doc === document ? pdfView.querySelector(".textLayer") : doc?.body;
  const view = doc?.defaultView;
  wordRanges = [];
  wordDocument = doc;
  if (!surface || !view?.CSS?.highlights || !view.Highlight) return;
  const dictionary = new Map(activeWords().map(word => [word.word_key, word]));
  const highlights = new view.Highlight();
  view.CSS.highlights.set("modu-words", highlights);
  if (!dictionary.size) return;
  const walker = doc.createTreeWalker(surface, NodeFilter.SHOW_TEXT);
  const groups = [];
  let node;
  let block;
  while ((node = walker.nextNode())) {
    if (node.parentElement.closest("script, style, noscript, button, textarea, svg")) continue;
    const parent = node.parentElement.closest("p, li, div, h1, h2, h3, h4, h5, h6, td, th, pre") || surface;
    if (parent !== block) { groups.push([]); block = parent; }
    groups.at(-1).push(node);
  }
  for (const nodes of groups) {
    const text = nodes.map(node => node.textContent).join("");
    const offsets = [];
    let offset = 0;
    for (const node of nodes) { offsets.push(offset); offset += node.length; }
    for (const match of text.matchAll(/\p{L}[\p{L}\p{M}]*(?:['’\-][\p{L}\p{M}]+)*/gu)) {
      const entry = dictionary.get(wordKey(match[0]));
      if (!entry) continue;
      const start = match.index;
      const end = start + match[0].length;
      const first = nodes.findIndex((node, i) => offsets[i] + node.length > start);
      const last = nodes.findIndex((node, i) => offsets[i] + node.length >= end);
      const range = doc.createRange();
      range.setStart(nodes[first], start - offsets[first]);
      range.setEnd(nodes[last], end - offsets[last]);
      highlights.add(range);
      wordRanges.push({range, entry});
    }
  }
}

function bindVocabulary(doc) {
  doc.addEventListener("click", event => {
    if (dialog.open || doc !== wordDocument || !doc.getSelection()?.isCollapsed) return;
    if (event.target.closest("a, button, input, select, textarea")) return;
    const hit = wordRanges.find(({range}) => [...range.getClientRects()].some(rect =>
      event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom));
    if (hit) {
      const box = doc === document ? {left: 0, top: 0} : frame.getBoundingClientRect();
      showSavedWord(hit.entry, hit.range, doc, box);
    }
  });
}

function showSavedWord(entry, range, doc, box) {
  clearSelection();
  const selected = doc.getSelection();
  selected.removeAllRanges();
  selected.addRange(range.cloneRange());
  selection = selected.toString().trim();
  $("selection-engine").textContent = entry.word;
  $("selection-engine").classList.remove("is-passage");
  $("selection-result").textContent = entry.translation;
  $("selection-pronunciation").replaceChildren(...speechButtons(entry.word, entry.source));
  $("selection-actions").replaceChildren(...wordButtons(entry.word, {
    text: entry.translation, source: entry.source, target: entry.target,
  }));
  $("selection-source").textContent = label("manageWord");
  $("selection-source").onclick = () => editWord(entry);
  selectionPreview.hidden = false;
  placeSelection(selectionPreview, selected, box);
}

async function vocabulary() {
  if (!shelfData.serverVersion) return toast(label("restartRequired"));
  try {
    words = await api("api/vocabulary");
    highlightWords();
    const search = element("input");
    search.type = "search";
    search.placeholder = label("filterWords");
    search.setAttribute("aria-label", label("filterWords"));
    const list = element("div", null, "word-list");
    function render() {
      const query = wordKey(search.value);
      const entries = words.filter(word => wordKey(word.word).includes(query) || word.translation.toLowerCase().includes(query));
      list.replaceChildren(...entries.map(entry => {
        const row = element("div", null, "word-row");
        const open = button("", () => editWord(entry));
        open.setAttribute("aria-label", entry.word + " · " + entry.translation);
        const content = element("span", null, "word-summary");
        content.append(element("strong", entry.word), element("span", entry.translation, "muted"));
        open.append(content, icon("chevron"));
        row.append(open);
        return row;
      }));
      if (!entries.length) list.append(element("p", label("noWords"), "muted"));
    }
    search.oninput = render;
    render();
    const nodes = [search, element("p", String(words.length) + " · " + label("vocabulary"), "muted word-count"), list];
    if (!window.CSS?.highlights) nodes.push(element("p", label("highlightUnavailable"), "muted"));
    showDialog(label("vocabulary"), nodes);
  } catch (error) { report(error); }
}

function editWord(entry) {
  const field = element("label", label("meaning"));
  const meaning = element("textarea");
  meaning.value = entry.translation;
  meaning.maxLength = 4000;
  field.append(meaning);
  const actions = element("div", null, "word-actions");
  actions.append(
    button(label("save"), async () => {
      try {
        words = await api("api/vocabulary", {...entry, translation: meaning.value});
        await vocabulary();
      } catch (error) { report(error); }
    }), button(label("delete"), () => confirmAction(label("delete"), label("removeWord"), async () => {
      words = await api("api/vocabulary", {...entry, remove: true});
      await vocabulary();
    })));
  showDialog(entry.word, [...speechButtons(entry.word, entry.source), field, actions], "lookup-dialog");
}

function showImage(url, alt) {
  const image = element("img");
  image.alt = alt;
  image.hidden = true;
  const stage = element("div", null, "image-stage");
  stage.append(image);
  const viewport = element("div", null, "image-viewport");
  viewport.tabIndex = 0;
  viewport.setAttribute("aria-label", alt);
  viewport.append(stage);
  const percent = element("output");
  let scale = 0;
  const fitScale = () => Math.min(1, viewport.offsetWidth / image.naturalWidth, viewport.offsetHeight / image.naturalHeight);
  function update() {
    if (!image.naturalWidth) return;
    const zoom = scale || fitScale();
    image.style.width = Math.max(1, Math.floor(image.naturalWidth * zoom)) + "px";
    image.hidden = false;
    percent.textContent = Math.round(zoom * 100) + "%";
    smaller.disabled = zoom <= fitScale() + 0.001;
    larger.disabled = zoom >= 4;
  }
  const fit = button(label("fit"), () => { scale = 0; update(); });
  const smaller = button("−", () => { scale = Math.max(fitScale(), (scale || fitScale()) / 1.5); update(); });
  const larger = button("+", () => { scale = Math.min(4, (scale || fitScale()) * 1.5); update(); });
  smaller.setAttribute("aria-label", label("zoomOut"));
  larger.setAttribute("aria-label", label("zoomIn"));
  fit.disabled = smaller.disabled = larger.disabled = true;
  const toolbar = element("div", null, "image-toolbar");
  toolbar.append(fit, smaller, larger, percent);
  const observer = new ResizeObserver(update);
  dialog.addEventListener("close", () => observer.disconnect(), {once: true});
  image.onload = () => { fit.disabled = false; update(); };
  image.onerror = () => {
    toolbar.hidden = true;
    viewport.replaceChildren(element("p", label("imageError")));
  };
  showDialog(label("image"), [toolbar, viewport], "image-dialog");
  observer.observe(viewport);
  image.src = url;
}

async function addMark() {
  if (!isReady()) return;
  const item = book;
  try {
    const result = await api(bookPath(item) + "/mark", {...spot});
    item.marks = result.marks;
    toast(label("marked"));
  } catch (error) { report(error); }
}

function marks() {
  if (!book) return;
  const item = book;
  const nodes = item.marks.map(mark => {
    const row = element("div", null, "mark-row");
    const name = item.chapters[mark.index]?.label || label("page") + " " + (mark.index + 1);
    row.append(button(name + " · " + Math.round(mark.scroll * 100) + "%", () => {
      dialog.close();
      jump(mark);
    }), button(label("delete"), async () => {
      try {
        item.marks = (await api(bookPath(item) + "/mark", {...mark, remove: true})).marks;
        marks();
      } catch (error) { report(error); }
    }));
    return row;
  });
  showDialog(label("marks"), nodes.length ? nodes : [element("p", label("noMarks"))]);
}

function keyboard(event) {
  const tag = event.target.tagName;
  if (event.key === "Escape" && !selectionPreview.hidden) {
    clearSelection();
    event.preventDefault();
    return;
  }
  if (event.ctrlKey || event.metaKey || event.altKey || dialog.open || ["INPUT", "SELECT", "TEXTAREA"].includes(tag)) return;
  const direction = ["ArrowRight", "PageDown"].includes(event.key) || (event.key === " " && tag !== "BUTTON") ? 1
    : ["ArrowLeft", "PageUp"].includes(event.key) ? -1 : 0;
  if (direction && isReady()) {
    event.preventDefault();
    navigate(direction);
    return;
  }
  if (tag === "BUTTON") return;
  const actions = {
    c: () => $("toc-button").click(), b: addMark, s: settings, "/": searchBook, w: vocabulary,
    t: () => $("theme-button").click(),
  };
  if (actions[event.key]) { event.preventDefault(); actions[event.key](); }
}

$("settings-button").onclick = settings;
$("search-button").onclick = searchBook;
$("vocabulary-button").onclick = vocabulary;
dialog.addEventListener("close", stopSpeech);
bindVocabulary(document);
$("shelf-button").onclick = $("back-button").onclick = backToShelf;
$("archive-toggle").onclick = () => { archived = !archived; renderShelf(); };
$("theme-button").onclick = () => {
  const names = Object.keys(shelfData.themes);
  setTheme(names[(names.indexOf(theme) + 1) % names.length]);
};
$("toc-button").onclick = () => { sidebarOpen = !sidebarOpen; syncSidebar(); };
matchMedia("(max-width: 720px)").addEventListener("change", event => {
  sidebarOpen = !event.matches;
  syncSidebar();
});
$("previous").onclick = () => navigate(-1);
$("next").onclick = () => navigate(1);
$("mark-button").onclick = addMark;
$("marks-button").onclick = marks;
$("selection").addEventListener("mousedown", event => event.preventDefault());
$("selection").onclick = () => selectionDialog();
selectionPreview.addEventListener("mousedown", event => event.preventDefault());
$("selection-close").onclick = clearSelection;
$("selection-source").onclick = () => selectionDialog(false);
new ResizeObserver(() => {
  const selected = previewDocument?.getSelection();
  if (selectionPreview.hidden || !selected?.rangeCount) return;
  const box = previewDocument === document ? {left: 0, top: 0} : frame.getBoundingClientRect();
  placeSelection(selectionPreview, selected, box);
}).observe(selectionPreview);
bindSelection(document, pdfView, () => ({left: 0, top: 0}));
document.addEventListener("keydown", keyboard);
$("import-button").onclick = () => {
  if (!shelfData) return;
  showDialog(label("import"), [
    element("p", label("importNote") + " " + label("copyNote")),
    element("p", label("copyDirectory"), "muted"),
    element("p", shelfData.copyPath, "copy-path"),
    button(label("chooseFile"), () => { dialog.close(); $("import-file").click(); }),
  ]);
};
$("import-file").onchange = async event => {
  const file = event.target.files[0];
  event.target.value = "";
  if (!file) return;
  toast(label("importing"));
  try {
    const result = await api("api/import", undefined, {
      method: "POST", body: file,
      headers: {"Content-Type": "application/octet-stream", "X-MODU-Filename": encodeURIComponent(file.name)},
    });
    await openBook(result.id);
  } catch (error) { report(error); }
};
let resizeTimer;
new ResizeObserver(() => {
  clearTimeout(resizeTimer);
  if (!pager || pager.layout === pager.geometry) return;
  clearSelection();
  pageHistory.length = 0;
  if (pdfDocument && !pdfView.hidden) {
    resizeTimer = setTimeout(() => renderPdf().catch(report), 180);
  } else if (pager.resize(spot)) updatePosition();
}).observe($("viewport"));
addEventListener("pagehide", savePosition);
try {
  await loadShelf();
  if (shelfData.start && shelfData.books.some(item => item.id === shelfData.start && (shelfData.explicitBook || !item.archived))) {
    await openBook(shelfData.start);
  }
} catch (error) { report(error); }
