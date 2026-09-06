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
        self.open_graph_images: list[str | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        self.tags.append(tag)
        if tag == "meta" and values.get("property") == "og:image":
            self.open_graph_images.append(values.get("content"))
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

    def test_open_graph_image_has_an_absolute_deployed_asset_url(self) -> None:
        self.assertEqual(
            self.parser().open_graph_images,
            ["https://jcmaker.github.io/DashPi/assets/dashpi-incidents.jpg"],
        )

    def test_hero_art_has_a_korean_no_javascript_label(self) -> None:
        self.assertIn(
            'role="img" aria-label="사고 전후 영상 보존과 광학 전송을 표현한 기하학 구성"', self.page()
        )

    def test_hero_art_uses_a_responsive_incident_motif(self) -> None:
        page = self.page()
        styles = (LANDING / "styles.css").read_text(encoding="utf-8")
        self.assertNotIn("SHA<br>256", page)
        self.assertNotIn("verification-square", page + styles)
        self.assertIn('class="incident-window"', page)
        self.assertIn('class="clip-strip"', page)
        self.assertIn(".incident-window", styles)
        self.assertIn(".clip-strip", styles)

    def test_grid_theme_contract(self) -> None:
        tokens = (LANDING / "tokens.css").read_text(encoding="utf-8")
        styles = (LANDING / "styles.css").read_text(encoding="utf-8")
        expected_tokens = {
            "--color-paper": "oklch(99% 0.003 255)",
            "--color-ink": "oklch(16% 0.010 255)",
            "--color-rule": "oklch(88% 0.006 255)",
            "--color-accent": "oklch(55% 0.21 28)",
            "--font-display": '"Archivo", "Noto Sans KR", "Helvetica Neue", Arial, sans-serif',
        }
        for name, value in expected_tokens.items():
            self.assertIn(f"{name}: {value};", tokens)
        self.assertIn("--color-rail: oklch(95.5% 0.003 255);", tokens)
        self.assertIn("var(--color-rail) 0", styles)
        self.assertIn("body > header, body > main, body > footer { position: relative; z-index: 1; }", styles)
        self.assertIn(".topbar__controls { grid-column: 6 / 13; grid-row: 1; }", styles)
        self.assertIn("repeat(12, minmax(0, 1fr))", styles)
        self.assertIn("overflow-x: clip", styles)
        self.assertIn("prefers-reduced-motion: reduce", styles)
        self.assertNotIn("box-shadow:", styles)
        self.assertNotIn("linear-gradient(135deg", styles)

    def test_stylesheets_are_linked(self) -> None:
        parser = self.parser()
        self.assertTrue({"tokens.css", "styles.css"} <= parser.assets)

    def translations(self) -> dict[str, dict[str, str]]:
        match = re.search(
            r'<script id="translations" type="application/json">(.*?)</script>',
            self.page(),
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        return json.loads(match.group(1))

    def test_translation_keys_match_and_cover_the_page(self) -> None:
        translations = self.translations()
        self.assertEqual(set(translations), {"ko", "en"})
        self.assertEqual(set(translations["ko"]), set(translations["en"]))
        parser = self.parser()
        referenced = parser.i18n_keys | parser.i18n_attr_keys
        self.assertLessEqual(referenced, set(translations["ko"]))
        self.assertTrue(all(translations[lang][key].strip() for lang in translations for key in translations[lang]))

    def test_copy_covers_the_current_analysis_report_flow(self) -> None:
        translations = self.translations()
        expected = {
            "ko": ("사고 시점", "앞뒤 5초", "오버레이", "PDF", "재생성", "낮은 품질"),
            "en": ("accident moment", "5 seconds", "overlay", "PDF", "regeneration", "lower quality"),
        }
        for language, phrases in expected.items():
            copy = " ".join(translations[language].values())
            for phrase in phrases:
                self.assertIn(phrase, copy)

    def test_script_has_safe_korean_fallback(self) -> None:
        script = (LANDING / "script.js").read_text(encoding="utf-8")
        self.assertIn('const DEFAULT_LANGUAGE = "ko";', script)
        self.assertIn("try", script)
        self.assertIn("localStorage", script)

    def test_script_is_linked(self) -> None:
        self.assertIn("script.js", self.parser().assets)

    def test_pages_workflow_publishes_landing_directory(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertIn("actions/configure-pages@v5", workflow)
        self.assertIn("actions/upload-pages-artifact@v3", workflow)
        self.assertIn("actions/deploy-pages@v4", workflow)
        self.assertIn("path: landing", workflow)
        self.assertIn("pages: write", workflow)
        self.assertIn("id-token: write", workflow)
