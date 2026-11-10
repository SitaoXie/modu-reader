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
let toastTimer;
let saveTimer;
let bookGeneration = 0;
let pdfGeneration = 0;
let pdfDocument;
let pdfEngine;
let pdfTask;
let pager;
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
  clearSelection();
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
  $("next").disabled = !pager || (spot.index === count - 1 && pager.end >= pager.extent - 1);
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
  Object.assign(spot, pager.position);
  updateProgress();
  rememberPosition();
}

function jump(value, fragment = "", turning = false) {
  if (!book || !total()) return;
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
  const contentWindow = frame.contentWindow;
  const index = currentFrameIndex();
  if (index >= 0) spot.index = index;
  const previous = pendingFrame;
  pendingFrame = undefined;
  clearPager();
  if (doc.scrollingElement) {
    pager = new ScreenPages(doc.scrollingElement, frame, doc.body);
    if (previous?.url === contentWindow.location.pathname && !previous.fragment) {
      pager.restore(previous.position, previous.endRatio);
    } else {
      if (previous?.fragment) frameAnchor(doc, previous.fragment)?.scrollIntoView();
      else if (!previous) pageHistory.length = 0;
      pager.prepare();
    }
  }
  doc.addEventListener("scroll", onFrameScroll, {passive: true});
  doc.addEventListener("keydown", keyboard);
  bindSelection(doc, doc, () => frame.getBoundingClientRect());
  if (book.format === "epub") bindImages(doc);
  onFrameScroll();
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
  updatePosition();
}

pdfView.addEventListener("scroll", () => {
  if (!selectionPreview.hidden) clearSelection();
  if (book?.format === "pdf" && !pdfView.hidden) updatePosition();
}, {passive: true});

function navigate(delta) {
  if (!isReady()) return;
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
  if (!moreHere && spot.index >= total() - 1) return;
  pageHistory.push({index: spot.index, ...pager.position, endRatio: next / pager.extent});
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
        await saveTranslationOption(select, {provider: select.value}, "provider");
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
      select.value = updated.global_target;
      toast(label("saved"));
    });
    const nodes = [engine, notice, automaticField, global];
    if (item) nodes.push(selectField(label("bookTarget"), [["", label("inherit")], ...choices], value.book_target, async select => {
      item.translation = await api(bookPath(item) + "/translation", {target: select.value});
      toast(label("saved"));
    }));
    showDialog(label("settings"), nodes);
  } catch (error) { report(error); }
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
}

function readingSelection(doc) {
  if (!book || dialog.open || (doc !== document && (frame.hidden || frame.contentDocument !== doc))) return;
  const range = doc.getSelection();
  if (!range?.rangeCount || range.isCollapsed) return;
  if (doc === document && (pdfView.hidden || !pdfView.contains(range.anchorNode) || !pdfView.contains(range.focusNode))) return;
  return range;
}

function placeSelection(node, range, box) {
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
  const {provider} = translationOptions();
  const request = new AbortController();
  translationRequest = request;
  $("selection-engine").textContent = label(provider);
  const output = $("selection-result");
  output.textContent = translating(provider);
  selectionPreview.hidden = false;
  placeSelection(selectionPreview, range, getBox());
  try {
    const result = await api(bookPath(item) + "/translate", {text, source: initialSource(item), provider}, {signal: request.signal});
    if (!request.signal.aborted) output.textContent = result.text;
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
  try {
    const pref = (await api(bookPath(item))).translation;
    if (book !== item) return;
    const {provider} = translationOptions();
    const options = Object.entries(shelfData.languages);
    const source = selectField(label("source"), [["", label("auto")], ...options], initialSource(item));
    const description = element("p", label("target") + " · " + (shelfData.languages[pref.target] || pref.target));
    const output = element("div", "", "translation-result");
    output.hidden = true;
    output.setAttribute("aria-live", "polite");
    const go = button(label("translate"), async () => {
      go.disabled = true;
      output.hidden = false;
      output.textContent = translating(provider);
      try {
        const result = await api(bookPath(item) + "/translate", {text, source: source.querySelector("select").value, provider});
        output.textContent = result.text;
      } catch (error) { output.textContent = label(error.message); }
      finally { go.disabled = false; }
    });
    showDialog(label("translate") + " · " + label(provider),
      [source, description, element("p", translationNotice(provider), "muted"), go, output]);
    if (start) go.click();
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
    if (!imageSource(image)) continue;
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
    c: () => $("toc-button").click(), b: addMark, s: settings,
    t: () => $("theme-button").click(),
  };
  if (actions[event.key]) { event.preventDefault(); actions[event.key](); }
}

$("settings-button").onclick = settings;
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
