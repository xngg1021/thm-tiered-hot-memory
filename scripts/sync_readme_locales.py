#!/usr/bin/env python3
"""Embed standalone localized READMEs as in-page language panels in README.md."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES = [
    ("zh-CN", "简体中文", "README.zh-CN.md"),
    ("zh-TW", "繁體中文", "README.zh-TW.md"),
    ("ja", "日本語", "README.ja.md"),
    ("ko", "한국어", "README.ko.md"),
    ("es", "Español", "README.es.md"),
    ("fr", "Français", "README.fr.md"),
    ("de", "Deutsch", "README.de.md"),
]


def body(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].startswith("# THM"):
        raise ValueError(f"unexpected localized README header: {path.name}")
    # Drop the repeated title, language-navigation row and surrounding blanks.
    return "\n".join(lines[4:]).strip() + "\n"


def main() -> None:
    target = ROOT / "README.md"
    text = target.read_text(encoding="utf-8")
    start = "<!-- in-page-locales:start -->"
    end = "<!-- in-page-locales:end -->"
    if start in text:
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
    else:
        lines = text.splitlines(keepends=True)
        navigation = next(i for i, line in enumerate(lines) if line.startswith("[English](README.md)"))
        before = "".join(lines[:navigation])
        after = "".join(lines[navigation + 1:])
    panels = [start, "", "**Language / 语言 / 言語 / 언어 / Idioma / Langue / Sprache**", ""]
    for code, label, filename in LOCALES:
        panels.extend([
            f'<details id="readme-{code}">',
            f"<summary><strong>{label}</strong></summary>",
            "",
            f"<!-- locale:{code}:start -->",
            body(ROOT / filename).rstrip(),
            f"<!-- locale:{code}:end -->",
            "",
            "</details>",
            "",
        ])
    panels.extend([end, ""])
    target.write_text(before.rstrip() + "\n\n" + "\n".join(panels) + after.lstrip(), encoding="utf-8")


if __name__ == "__main__":
    main()
