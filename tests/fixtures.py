"""Original project test material, generated locally without downloaded books/fonts."""

from pathlib import Path

PARAGRAPH = "“灯塔亮了，船还没到。”小岚合上笔记，看向窗外；雨滴落在栏杆上，留下细小的圆点。她写下：「明天，我们沿着河岸走一走。」"


def original_book(chapters=12, paragraphs=35):
    return "\n\n".join(
        f"第{chapter}章 河岸来信\n\n"
        + "\n\n".join(f"{number:04d} {PARAGRAPH}" for number in range(1, paragraphs + 1))
        for chapter in range(1, chapters + 1)
    )


def make_pdf(path: Path, *, blank=False, encrypted=False):
    from pypdf import PdfWriter
    from pypdf.generic import (
        DictionaryObject,
        NameObject,
        NumberObject,
        ArrayObject,
        TextStringObject,
        DecodedStreamObject,
    )

    writer = PdfWriter()
    page = writer.add_blank_page(612, 792)
    if not blank:
        # Standard CJK Type 0 font + explicit ToUnicode mapping. No external font asset.
        descendant = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/CIDFontType0"),
                NameObject("/BaseFont"): NameObject("/STSong-Light"),
                NameObject("/DW"): NumberObject(1000),
                NameObject("/CIDSystemInfo"): DictionaryObject(
                    {
                        NameObject("/Registry"): TextStringObject("Adobe"),
                        NameObject("/Ordering"): TextStringObject("GB1"),
                        NameObject("/Supplement"): NumberObject(4),
                    }
                ),
            }
        )
        text = "中文标点，测试。"
        mapping = "\n".join(f"<{ord(c):04X}> <{ord(c):04X}>" for c in sorted(set(text)))
        cmap = DecodedStreamObject()
        cmap.set_data(
            (
                """/CIDInit /ProcSet findresource begin
12 dict begin begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def
/CMapName /ModuOriginal def /CMapType 2 def
1 begincodespacerange <0000> <FFFF> endcodespacerange
"""
                + str(len(set(text)))
                + " beginbfchar\n"
                + mapping
                + "\nendbfchar\nendcmap\nCMapName currentdict /CMap defineresource pop end end"
            ).encode("ascii")
        )
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type0"),
                NameObject("/BaseFont"): NameObject("/STSong-Light"),
                NameObject("/Encoding"): NameObject("/Identity-H"),
                NameObject("/DescendantFonts"): ArrayObject([writer._add_object(descendant)]),
                NameObject("/ToUnicode"): writer._add_object(cmap),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        content = DecodedStreamObject()
        content.set_data(
            f"BT /F1 12 Tf 72 720 Td <{text.encode('utf-16-be').hex()}> Tj ET".encode("ascii")
        )
        page[NameObject("/Contents")] = writer._add_object(content)
        writer.add_outline_item("目录标题", 0)
    if encrypted:
        writer.encrypt("test-only-password")
    with path.open("wb") as target:
        writer.write(target)
