"""Independent terminal width variants; never import MODU's layout functions.

These models stress differing terminal/font policies. They are not a claim to
emulate every behavior of a specific GUI terminal.
"""

import unicodedata
from unittest.mock import patch
import pyte
import pyte.screens

DEFAULT_WIDTH = pyte.screens.wcwidth


class WidthVariantScreen(pyte.Screen):
    def __init__(self, columns, lines, model="standard"):
        self.width_model = model
        super().__init__(columns, lines)

    def terminal_width(self, char):
        width = DEFAULT_WIDTH(char)
        if (
            self.width_model == "narrow-punctuation"
            and unicodedata.category(char).startswith("P")
            and width == 2
        ):
            return 1
        if (
            self.width_model == "wide-ambiguous"
            and unicodedata.east_asian_width(char) == "A"
            and width == 1
        ):
            return 2
        return width

    def draw(self, data):
        # pyte 0.8 stops an entire draw chunk at a zero-cell, non-combining
        # format character. U+2060 is invisible and must not discard the text
        # after it. Pixel tests still replay the original, unmodified bytes.
        data = data.replace("\u2060", "")
        with patch("pyte.screens.wcwidth", self.terminal_width):
            return super().draw(data)
