"""Fluent-style dark theme for the native Qt app, scaled up for a touch LCD."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

ASSETS = Path(__file__).parent / "assets"

# WinUI dark-theme values; sizes are enlarged from Fluent's 32px desktop controls for touch.
TOKENS = {
    "bg": "#202020",
    "card": "#2b2b2b",
    "control": "#2d2d2d",
    "control_hover": "#353535",
    "control_pressed": "#272727",
    "stroke": "#3a3a3a",
    "stroke_top": "#454545",
    "text": "#ffffff",
    "text_secondary": "#c5c5c5",
    "text_disabled": "#787878",
    "accent": "#0078d4",
    "accent_hover": "#1a86d9",
    "accent_pressed": "#006cbe",
    "accent_text": "#ffffff",
    "critical": "#c42b1c",
    "critical_hover": "#d13a2b",
    "critical_text": "#ff99a4",
    "radius": "6px",
    "radius_card": "10px",
    "body": "18px",
    "subtitle": "22px",
    "title": "30px",
}

STYLE = """
* {{ font-family: "Pretendard"; }}
QWidget {{ background: {bg}; color: {text}; font-size: {body}; }}
QLabel {{ background: transparent; }}
QLabel#title {{ font-size: {title}; font-weight: 600; padding: 2px 0 6px 0; }}
QLabel#rec {{ font-size: {title}; font-weight: 600; color: {critical_text}; }}
QLabel#status, QLabel#caption {{ color: {text_secondary}; }}
QLabel#clock {{ color: {text_secondary}; font-size: {subtitle}; }}

QPushButton, QToolButton, QComboBox, QLineEdit, QDoubleSpinBox {{
  background: {control}; color: {text};
  border: 1px solid {stroke}; border-top-color: {stroke_top};
  border-radius: {radius}; min-height: 52px; padding: 4px 18px;
}}
QPushButton {{ min-width: 120px; }}
QPushButton:hover, QToolButton:hover, QComboBox:hover {{ background: {control_hover}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {control_pressed}; color: {text_secondary}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {text_disabled}; background: {control_pressed}; }}

QPushButton#primary, QToolButton#primary {{
  background: {accent}; color: {accent_text}; border: 1px solid {accent_hover}; font-weight: 600;
}}
QPushButton#primary:hover, QToolButton#primary:hover {{ background: {accent_hover}; }}
QPushButton#primary:pressed, QToolButton#primary:pressed {{ background: {accent_pressed}; }}
QPushButton#primary:disabled {{ background: {control_pressed}; color: {text_disabled}; border-color: {stroke}; }}
QPushButton#danger {{ background: {critical}; color: {text}; border: 1px solid {critical_hover}; }}
QPushButton#danger:hover {{ background: {critical_hover}; }}

QToolButton {{
  background: {card}; border-radius: {radius_card}; min-height: 180px; min-width: 150px;
  font-size: {subtitle}; font-weight: 600; padding: 22px 12px 16px 12px;
}}

QLineEdit:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-bottom: 2px solid {accent}; }}
QComboBox::drop-down {{ border: none; width: 44px; }}
QComboBox::down-arrow {{ image: url({chevron}); width: 20px; height: 20px; }}
QComboBox QAbstractItemView {{
  background: {card}; border: 1px solid {stroke}; selection-background-color: {control_hover};
  outline: none; padding: 4px;
}}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}

QListWidget {{
  background: {card}; border: 1px solid {stroke}; border-radius: {radius_card};
  padding: 6px; outline: none;
}}
QListWidget::item {{ min-height: 52px; padding: 0 14px; border-radius: {radius}; margin: 2px 0; }}
QListWidget::item:hover {{ background: {control_hover}; }}
QListWidget::item:selected {{
  background: {control_hover}; color: {text}; border-left: 4px solid {accent};
}}

QScrollArea {{ border: 1px solid {stroke}; border-radius: {radius_card}; background: {card}; }}
QScrollArea > QWidget > QWidget {{ background: {card}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {stroke_top}; border-radius: 3px; min-height: 40px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
  background: none; height: 0;
}}
""".format(**TOKENS, chevron=(ASSETS / "chevron-down.png").as_posix())


def icon(name: str) -> QIcon:
    return QIcon(str(ASSETS / f"{name}.png"))


def apply(app: QApplication) -> None:
    for font in ("Pretendard-Regular.otf", "Pretendard-SemiBold.otf"):
        QFontDatabase.addApplicationFont(str(ASSETS / font))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
