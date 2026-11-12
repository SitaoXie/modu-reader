"""Terminal lookup and vocabulary UI backed by the same library as the Web reader."""

import asyncio

from rich.text import Text
from textual import on, work
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, OptionList, Select, Static, TextArea
from textual.widgets.option_list import Option

from .translation import (
    LANGUAGES, TranslationError, options_for, set_option, set_target, settings_for,
    translate_selection,
)
from .vocabulary import word_key
from .terminal_audio import play

LABELS = {
    "title": ("划词翻译", "Translate selection"),
    "settings": ("翻译设置", "Translation settings"),
    "engine": ("翻译引擎", "Translation engine"),
    "local": ("本地 · Argos", "On-device · Argos"),
    "google": ("Google 网页翻译", "Google Translate Web"),
    "youdao": ("有道网页翻译", "Youdao Web"),
    "notice": ("在线引擎会发送选中文字。查询音标、英美发音会将单词发送给有道。", "Online engines send the selected text. IPA and UK/US audio send the word to Youdao."),
    "local_note": ("本地翻译首次使用需下载模型；可在设置中切换免登录网页引擎。", "On-device translation downloads models on first use. Settings also offers web engines without sign-in."),
    "automatic": ("划选后自动翻译", "Translate automatically after selection"),
    "global": ("全局目标语言", "Default target language"),
    "book": ("仅本书目标语言", "Target for this book"),
    "inherit": ("沿用全局默认", "Use global default"),
    "system": ("跟随系统", "Follow system"),
    "source": ("原文语言", "Source language"),
    "auto": ("自动识别", "Auto detect"),
    "original": ("原文（最多 600 字）", "Original text (up to 600 characters)"),
    "lookup": ("翻译", "Translate"),
    "busy": ("正在翻译…", "Translating…"),
    "local_busy": ("准备模型或翻译中… 首次使用可能需要几分钟。", "Preparing models or translating… First use may take a few minutes."),
    "save": ("加入生词本", "Save word"),
    "saved": ("已收藏 · 再按取消", "Saved · Press to remove"),
    "ipa": ("查询音标", "Look up IPA"),
    "no_ipa": ("暂无音标", "IPA unavailable"),
    "speech": ("▶ 本地", "▶ Local"),
    "close": ("返回 Esc", "Back Esc"),
    "vocabulary": ("生词本", "Vocabulary"),
    "filter": ("查找生词", "Find a word"),
    "empty": ("还没有生词。划选单词后按 f 翻译并收藏。", "No saved words. Select a word, press f to translate, then save."),
    "edit": ("编辑译文", "Edit meaning"),
    "apply": ("保存译文", "Save meaning"),
    "hint": ("鼠标拖选文字 · f 翻译 · w 生词本 · 点击标注词查看译文", "Drag to select · f Translate · w Vocabulary · Click a marked word"),
    "too_long": ("请选择 1 至 600 个字符。", "Select 1 to 600 characters."),
    "unsupported_language": ("不支持这组语言，请更换原文或目标语言。", "Language pair unavailable. Change the source or target."),
    "dependencies": ("请安装 translation 扩展，或改用网页引擎。", "Install the translation extra, or choose a web engine."),
    "model_download": ("模型下载失败，请稍后重试。", "Model download failed. Please retry."),
    "translation_failed": ("翻译失败，请重试。", "Translation failed. Please retry."),
    "web_translation_failed": ("网页翻译暂时不可用，请重试或更换引擎。", "Web translation unavailable. Retry or change engines."),
    "youdao_language_pair": ("有道网页支持简体中文与英、日、韩、法、俄、西互译。", "Youdao supports Simplified Chinese paired with English, Japanese, Korean, French, Russian or Spanish."),
    "translation_provider_changed": ("引擎已更改，请重试。", "Engine changed. Please retry."),
    "invalid_book": ("这本书已不可用。", "Book unavailable."),
    "phonetics_failed": ("音标暂不可用，请重试。", "IPA unavailable. Please retry."),
    "speech_too_long": ("发音最多支持 200 个字符。", "Pronunciation supports up to 200 characters."),
    "speech_failed": ("发音不可用，请重试。", "Audio unavailable. Please retry."),
    "speech_unavailable": ("系统没有可用的播放器或语音。Linux 可安装 ffplay 和 espeak-ng。", "No player or voice available. On Linux, install ffplay and espeak-ng."),
    "failed": ("操作未完成，请重试。", "Could not complete the operation. Please retry."),
}


def label(app, key):
    return LABELS.get(key, LABELS["failed"])[app.language == "en"]


class LookupScreen(ModalScreen):
    BINDINGS = [("escape", "dismiss", "Back")]

    def tr(self, key):
        return label(self.app, key)

    def error(self, error):
        self.query_one("#lookup-status", Static).update(self.tr(getattr(error, "code", "failed")))


class TranslationSettings(LookupScreen):
    def compose(self):
        prefs = options_for(self.app.library)
        targets = settings_for(self.app.library, self.app.book_id)
        choices = [(name, key) for key, name in LANGUAGES.items()]
        with Vertical(classes="dialog lookup-dialog"):
            yield Label(self.tr("settings"), classes="dialog-title")
            with VerticalScroll(classes="lookup-body"):
                yield Label(self.tr("engine"))
                yield Select([(self.tr(key), key) for key in ("local", "google", "youdao")], value=prefs["provider"], allow_blank=False, id="translation-engine")
                yield Static(self.tr("notice"), classes="dialog-hint")
                yield Static(self.tr("local_note"), classes="dialog-hint")
                yield Checkbox(self.tr("automatic"), value=prefs["automatic"], id="translation-automatic")
                yield Label(self.tr("global"))
                yield Select([(self.tr("system") + " · " + LANGUAGES[targets["system_target"]], ""), *choices], value=targets["global_target"] or "", allow_blank=False, id="translation-global")
                if self.app.book_id:
                    yield Label(self.tr("book"))
                    yield Select([(self.tr("inherit"), ""), *choices], value=targets["book_target"] or "", allow_blank=False, id="translation-book")
                yield Static("", id="lookup-status")
            yield Button(self.tr("close"), id="lookup-close")

    @on(Select.Changed)
    def changed(self, event):
        if event.value is Select.BLANK:
            return
        if event.select.id == "translation-engine":
            set_option(self.app.library, {"provider": event.value})
        else:
            set_target(self.app.library, self.app.book_id if event.select.id == "translation-book" else None, event.value)
        self.app.refresh_vocabulary()

    @on(Checkbox.Changed)
    def automatic(self, event):
        set_option(self.app.library, {"automatic": event.value})

    @on(Button.Pressed, "#lookup-close")
    def close(self):
        self.dismiss()


class TranslationModal(LookupScreen):
    def __init__(self, text="", entry=None, automatic=False):
        super().__init__()
        text = " ".join(text.split())
        self.original = text
        self.entry = dict(entry) if entry else None
        self.automatic = automatic
        self.result = None
        self.revision = 0
        self.audio_worker = None
        self.input_snapshot = (text, self.entry["source"] if self.entry else "")

    def compose(self):
        with Vertical(classes="dialog lookup-dialog"):
            yield Label(self.tr("title"), classes="dialog-title")
            with VerticalScroll(classes="lookup-body"):
                yield Input(self.original, placeholder=self.tr("original"), max_length=600, id="lookup-original")
                yield Select([(self.tr("auto"), ""), *((name, key) for key, name in LANGUAGES.items())], value=self.entry["source"] if self.entry else "", allow_blank=False, id="lookup-source")
                yield Button(self.tr("lookup"), id="lookup-go", variant="primary")
                yield Static("", id="lookup-meaning")
                yield Static("", id="lookup-ipa")
                with Horizontal(classes="lookup-actions"):
                    yield Button("UK ▶", id="speak-uk")
                    yield Button("US ▶", id="speak-us")
                    yield Button(self.tr("speech"), id="speak-local")
                yield Button(self.tr("ipa"), id="lookup-phonetics")
                yield Button(self.tr("save"), id="lookup-save", disabled=True)
                yield Button(self.tr("edit"), id="lookup-edit")
                yield TextArea("", id="lookup-editor")
                yield Button(self.tr("apply"), id="lookup-apply")
                yield Static(self.tr("notice"), classes="dialog-hint")
                yield Static("", id="lookup-status")
            yield Button(self.tr("close"), id="lookup-close")

    def on_mount(self):
        for identity in ("lookup-editor", "lookup-apply", "lookup-edit"):
            self.query_one("#" + identity).display = False
        if self.entry:
            self.result = {"text": self.entry["translation"], "source": self.entry["source"], "target": self.entry["target"]}
            self.show_result()
            self.load_phonetics(False)
        elif self.automatic:
            self.lookup()
        else:
            self.query_one(Input).focus()

    @on(Input.Changed, "#lookup-original")
    @on(Select.Changed, "#lookup-source")
    def invalidate(self):
        current = (self.query_one(Input).value, self.query_one(Select).value)
        if current == self.input_snapshot:
            return
        self.input_snapshot = current
        self.revision += 1
        self.result = None
        self.query_one("#lookup-save", Button).disabled = True
        self.query_one("#lookup-meaning", Static).update("")
        self.query_one("#lookup-ipa", Static).update("")
        self.query_one("#lookup-edit").display = False
        if self.audio_worker:
            self.audio_worker.cancel()

    @on(Input.Submitted)
    @on(Button.Pressed, "#lookup-go")
    def submit(self):
        self.lookup()

    @work(exclusive=True, group="lookup")
    async def lookup(self):
        original = self.query_one(Input).value.strip()
        source = self.query_one(Select).value
        provider = options_for(self.app.library)["provider"]
        revision = self.revision
        self.result = None
        self.query_one("#lookup-save", Button).disabled = True
        self.query_one("#lookup-status", Static).update(self.tr("local_busy" if provider == "local" else "busy"))
        try:
            result = await asyncio.to_thread(translate_selection, self.app.library, self.app.book_id, original, source, provider)
            if revision != self.revision or not self.is_mounted:
                return
            self.result = result
            self.show_result()
            self.load_phonetics(provider != "local")
        except TranslationError as error:
            if revision == self.revision and self.is_mounted:
                self.error(error)

    def payload(self):
        return {"word": self.query_one(Input).value.strip(), "source": self.result["source"], "target": self.result["target"], "translation": self.result["text"]}

    def saved_entry(self):
        payload = self.payload()
        return next((entry for entry in self.app.vocabulary.entries() if entry["word_key"] == word_key(payload["word"]) and entry["source"] == payload["source"] and entry["target"] == payload["target"]), None)

    def show_result(self):
        self.query_one("#lookup-meaning", Static).update(Text(self.result["text"]))
        self.query_one("#lookup-status", Static).update("")
        save = self.query_one("#lookup-save", Button)
        try:
            saved = self.saved_entry()
        except ValueError:
            save.disabled = True
            return
        save.disabled = False
        save.label = self.tr("saved" if saved else "save")
        self.query_one("#lookup-edit").display = bool(saved)

    @on(Button.Pressed, "#lookup-save")
    def toggle(self):
        if not self.result:
            return
        self.app.vocabulary.update({**self.payload(), "remove": bool(self.saved_entry())})
        self.app.refresh_vocabulary()
        self.show_result()

    @on(Button.Pressed, "#lookup-edit")
    def edit(self):
        self.query_one("#lookup-editor", TextArea).load_text(self.result["text"])
        self.query_one("#lookup-editor").display = True
        self.query_one("#lookup-apply").display = True

    @on(Button.Pressed, "#lookup-apply")
    def apply(self):
        meaning = self.query_one(TextArea).text.strip()
        if self.result and 0 < len(meaning) <= 4000:
            self.result["text"] = meaning
            self.app.vocabulary.update(self.payload())
            self.app.refresh_vocabulary()
            self.query_one("#lookup-editor").display = False
            self.query_one("#lookup-apply").display = False
            self.show_result()

    @on(Button.Pressed, "#lookup-phonetics")
    def phonetics(self):
        self.load_phonetics(True)

    @work(exclusive=True, group="phonetics")
    async def load_phonetics(self, lookup):
        original = self.query_one(Input).value.strip()
        revision = self.revision
        try:
            result = await asyncio.to_thread(self.app.vocabulary.phonetics, {"word": original, "lookup": lookup})
            if revision == self.revision and self.is_mounted:
                self.query_one("#lookup-ipa", Static).update(Text("   ".join(f"{accent.upper()} /{value}/" for accent, value in result.items()) or (self.tr("no_ipa") if lookup else "")))
        except TranslationError as error:
            if revision == self.revision and self.is_mounted:
                self.error(error)
        except ValueError:
            pass  # Phrases have audio, but no single-word IPA entry.

    @on(Button.Pressed, "#speak-uk")
    @on(Button.Pressed, "#speak-us")
    @on(Button.Pressed, "#speak-local")
    def speak(self, event):
        self.audio_worker = self.audio(None if event.button.id == "speak-local" else event.button.id[-2:])

    @work(exclusive=True, group="audio")
    async def audio(self, accent):
        try:
            await play(self.query_one(Input).value.strip(), self.result["source"] if self.result else "en", accent)
        except TranslationError as error:
            if self.is_mounted:
                self.error(error)

    @on(Button.Pressed, "#lookup-close")
    def close(self):
        self.dismiss()

    def on_unmount(self):
        # Textual also cancels screen workers; explicitly stop any child player.
        if self.audio_worker:
            self.audio_worker.cancel()


class VocabularyModal(LookupScreen):
    def compose(self):
        with Vertical(classes="dialog lookup-dialog"):
            yield Label(self.tr("vocabulary"), classes="dialog-title")
            yield Input(placeholder=self.tr("filter"), id="vocabulary-filter")
            yield OptionList(id="vocabulary-entries")
            yield Static("", id="lookup-status")
            yield Button(self.tr("close"), id="lookup-close")

    def on_mount(self):
        self.populate()
        self.query_one(Input).focus()

    @on(Input.Changed)
    def populate(self):
        query = self.query_one(Input).value.casefold()
        self.entries = [entry for entry in self.app.vocabulary.entries() if query in (entry["word"] + " " + entry["translation"]).casefold()]
        options = self.query_one(OptionList)
        options.clear_options()
        options.add_options([Option(Text(f"{entry['word']} · {entry['target']}\n{entry['translation']}")) for entry in self.entries])
        if self.entries:
            options.highlighted = 0
        self.query_one("#lookup-status", Static).update("" if self.entries else self.tr("empty"))

    @on(OptionList.OptionSelected)
    def picked(self, event):
        entry = self.entries[event.option_index]
        self.app.push_screen(TranslationModal(entry["word"], entry), lambda _: self.populate())

    @on(Button.Pressed, "#lookup-close")
    def close(self):
        self.dismiss()
