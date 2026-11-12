"""Bounded chapter composition and text search for the loopback reader."""

from functools import lru_cache
from html import escape
import re
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup
import tinycss2 as css

from .safety import MAX_DOCUMENT_CHARS


def reading_options(library, change=None):
    rules = {"read_width": (64, 80, 96), "spacing": (0, 1, 2), "chapter_breaks": (False, True)}
    defaults = {"read_width": 80, "spacing": 1, "chapter_breaks": True}
    if change is not None:
        if not change or any(key not in rules for key in change):
            raise ValueError("Invalid reading preference")
        for key, value in change.items():
            if type(value) is not type(defaults[key]) or value not in rules[key]:
                raise ValueError("Invalid reading preference")
        for key, value in change.items():
            library.set_setting(key, value)
    result = {}
    for key, default in defaults.items():
        value = library.setting(key, default)
        result[key] = value if type(value) is type(default) and value in rules[key] else default
    return result


def normalized_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("style, script, head, [hidden]"):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text()).strip()


def scoped_selector(tokens):
    """Rewrite document elements, leaving class names, attributes and strings intact."""
    result = []
    for index, token in enumerate(tokens):
        previous = tokens[index - 1] if index else None
        if token.type == "ident" and token.lower_value in {"html", "body"} and not (
            previous and previous.type == "literal" and previous.value in {".", ":", "|"}
        ):
            result.append(".modu-" + token.lower_value)
        elif token.type == "ident" and token.lower_value == "root" and previous and previous.type == "literal" and previous.value == ":":
            result[-1] = ".modu-html"
        elif token.type == "function" and token.lower_name in {"is", "where", "not", "has"}:
            result.append(token.name + "(" + scoped_selector(token.arguments) + ")")
        else:
            result.append(token.serialize())
    return "".join(result)


def scoped_css(text, scope, importer, seen=None):
    seen = set() if seen is None else seen
    output = []
    for rule in css.parse_stylesheet(text, skip_comments=True, skip_whitespace=True):
        if rule.type == "qualified-rule":
            groups, current = [], []
            for token in rule.prelude:
                if token.type == "literal" and token.value == ",":
                    groups.append(current)
                    current = []
                else:
                    current.append(token)
            groups.append(current)
            selector = ",".join(scope + " " + scoped_selector(group) for group in groups)
            output.append(selector + "{" + css.serialize(rule.content) + "}")
        elif rule.type == "at-rule":
            if rule.lower_at_keyword in {"media", "supports", "layer"} and rule.content is not None:
                output.append("@" + rule.at_keyword + css.serialize(rule.prelude) + "{" + scoped_css(css.serialize(rule.content), scope, importer, seen) + "}")
            elif rule.lower_at_keyword == "import":
                tokens = [token for token in rule.prelude if token.type != "whitespace"]
                if not tokens:
                    continue
                token = tokens[0]
                url = token.value if token.type in {"string", "url"} else (
                    token.arguments[0].value if token.type == "function" and token.lower_name == "url" and len(token.arguments) == 1 and token.arguments[0].type == "string" else None
                )
                if url and url not in seen and len(seen) < 24:
                    seen.add(url)
                    imported = importer(url)
                    if imported:
                        rules = scoped_css(imported, scope, importer, seen)
                        condition = css.serialize(rule.prelude[rule.prelude.index(token) + 1:]).strip()
                        output.append(("@media " + condition + "{" + rules + "}") if condition else rules)
            elif rule.lower_at_keyword in {"font-face", "keyframes", "-webkit-keyframes"}:
                output.append(rule.serialize())
    # A style element is a raw-text HTML context, including when serialized by BS4.
    return "\n".join(output).replace("<", r"\3c ")


class WebContent:
    def __init__(self, reader):
        self.reader = reader
        self.section = lru_cache(maxsize=12)(self._section)
        self.search_text = lru_cache(maxsize=2)(self._search_text)

    def raw(self, identifier, index, prefix):
        book, source = self.reader.book(identifier)
        if book["format"].lower() == "epub":
            epub = self.reader.epub(source)
            if not 0 <= index < len(epub.chapters):
                raise FileNotFoundError
            name = epub.chapters[index].name
            mime, data = epub.resource(name, prefix=prefix)
            if mime == "image/svg+xml":
                data = f'<body><img src="{escape(prefix + name, quote=True)}"></body>'.encode()
            return data
        return self.reader.text_chapter(identifier, index)

    def _section(self, identifier, index, prefix):
        html = self.raw(identifier, index, prefix)
        soup = BeautifulSoup(html, "html.parser")
        styles = []
        for tag in soup.select("meta, title"):
            tag.decompose()
        book, source = self.reader.book(identifier)

        def importer(url):
            path = urlsplit(url).path
            if book["format"].lower() != "epub" or not path.startswith(prefix):
                return ""
            try:
                mime, data = self.reader.epub(source).resource(unquote(path[len(prefix):]), prefix=prefix)
                return data.decode("utf-8") if mime.startswith("text/css") else ""
            except (KeyError, ValueError):
                return ""

        scope = f'[data-modu-section="{index}"]'
        for tag in soup.select("style, link[rel=stylesheet]"):
            text = importer(tag.get("href", "")) if tag.name == "link" else tag.get_text()
            styles.append(scoped_css(text, scope, importer))
            tag.decompose()
        body = soup.body
        if body is None:
            if soup.head:
                soup.head.decompose()
            body = soup.new_tag("div")
            for node in list(soup.contents):
                if getattr(node, "name", None) or str(node).strip():
                    body.append(node.extract())
        body.name = "div"
        body["class"] = [*body.get("class", []), "modu-body"]
        root = soup.new_tag("div")
        if soup.html:
            root.attrs = dict(soup.html.attrs)
        root["class"] = [*root.get("class", []), "modu-html"]
        root.append(body.extract())
        section = soup.new_tag("section")
        section["data-modu-section"] = str(index)
        section.append(root)
        style = soup.new_tag("style")
        style.string = "\n".join(styles)
        section.insert(0, style)
        return str(section)

    def _search_text(self, identifier):
        book, source = self.reader.book(identifier)
        if book["format"].lower() == "pdf":
            raise ValueError("PDF search uses its rendered text layer")
        count = len(self.reader.epub(source).chapters) if book["format"].lower() == "epub" else len(self.reader.document(identifier).chapters)
        texts, size = [], 0
        for index in range(count):
            text = normalized_text(self.raw(identifier, index, "/publication/"))
            size += len(text)
            if size > MAX_DOCUMENT_CHARS:
                raise ValueError("Search text exceeds limit")
            texts.append(text)
        return texts

    def search(self, identifier, query):
        if not isinstance(query, str) or len(query) > 200:
            raise ValueError("Invalid search query")
        query = re.sub(r"\s+", " ", query).strip()
        results = []
        if not query:
            return {"results": [], "more": False}
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        for index, text in enumerate(self.search_text(identifier)):
            for occurrence, match in enumerate(pattern.finditer(text)):
                if len(results) == 200:
                    return {"results": results, "more": True}
                results.append({"index": index, "occurrence": occurrence,
                                "snippet": text[max(0, match.start() - 45):match.end() + 75]})
        return {"results": results, "more": False}
