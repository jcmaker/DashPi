from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import json
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "landing"


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.tags: list[str] = []
        self.assets: set[str] = set()
        self.i18n_keys: set[str] = set()
        self.i18n_attr_keys: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        self.tags.append(tag)
        if element_id := values.get("id"):
            self.ids.add(element_id)
        for name in ("src", "href"):
            value = values.get(name)
            if value and not value.startswith(("#", "http://", "https://", "mailto:")):
                self.assets.add(value)
        if key := values.get("data-i18n"):
            self.i18n_keys.add(key)
        if binding := values.get("data-i18n-attr"):
            self.i18n_attr_keys.add(binding.split(":", 1)[1])


class LandingPageTests(unittest.TestCase):
    def page(self) -> str:
        return (LANDING / "index.html").read_text(encoding="utf-8")

    def parser(self) -> PageParser:
        parser = PageParser()
        parser.feed(self.page())
        return parser

    def test_required_landmarks_sections_and_assets_exist(self) -> None:
        parser = self.parser()
        self.assertTrue({"header", "nav", "main", "section", "figure", "table", "footer"} <= set(parser.tags))
        self.assertTrue({"top", "flow", "evidence", "transfer", "verification", "source"} <= parser.ids)
        self.assertEqual(parser.tags.count("h1"), 1)
        for asset in parser.assets:
            self.assertTrue((LANDING / asset).is_file(), asset)

    def test_page_uses_dashpi_content_not_reference_content(self) -> None:
        page = self.page().lower()
        self.assertIn("dashpi", page)
        self.assertNotIn("signal, basel", page)
        self.assertNotIn("poster and graphic design festival", page)
