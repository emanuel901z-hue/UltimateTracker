#!/usr/bin/env python3
"""Prüft die Eltern-UI auf maschinell prüfbare WCAG-2.2-AA-Kriterien.

Aufruf:  python scripts/check-ui-a11y.py [pfad/zur/index.html]
Exit-Code 0 = alle Prüfungen bestanden (für die CI geeignet).

Geprüft wird:
- jedes Formularelement hat ein Label (for= oder umschließend) und einen Namen
- jeder Button hat einen zugänglichen Namen
- ARIA-Verweise (aria-controls/-labelledby/-describedby) zeigen auf existierende IDs
- Tab-Muster: role=tab/tabpanel, genau ein ausgewählter Tab, Roving tabindex
- Überschriftenreihenfolge ohne Sprünge, genau eine h1
- Sprachauszeichnung, Viewport ohne Zoom-Sperre
- Kontrast der Farb-Tokens (hell und dunkel) gegen WCAG AA
- Bedienziele: Mindesthöhe für interaktive Elemente
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

DEFAULT = Path("server/audio-bridge/app/static/index.html")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
FORM_CONTROLS = {"input", "select", "textarea"}
SKIP_INPUT_TYPES = {"hidden", "submit", "button", "reset", "checkbox", "radio"}


class Ui(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.aria_refs: list[tuple[str, str, str]] = []
        self.controls: list[dict] = []
        self.buttons: list[dict] = []
        self.headings: list[tuple[int, str]] = []
        self.labels_for: set[str] = set()
        self.wrapping_labels: list[list[str]] = []
        self.label_stack: list[list[str]] = []
        self.roles: list[tuple[str, str, dict]] = []
        self.tabs: list[dict] = []
        self.tabpanels: list[dict] = []
        self.html_lang = ""
        self.viewport = ""
        self._stack: list[tuple[str, dict]] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        element_id = attributes.get("id", "")
        if element_id:
            if element_id in self.ids:
                raise AssertionError(f"doppelte ID: {element_id}")
            self.ids.add(element_id)
        for key in ("aria-controls", "aria-labelledby", "aria-describedby"):
            if attributes.get(key):
                for reference in attributes[key].split():
                    self.aria_refs.append((key, reference, element_id or tag))
        if tag == "html":
            self.html_lang = attributes.get("lang", "")
        if tag == "meta" and attributes.get("name") == "viewport":
            self.viewport = attributes.get("content", "")
        if tag in FORM_CONTROLS and attributes.get("type") not in SKIP_INPUT_TYPES:
            self.controls.append({"tag": tag, "id": element_id, "attrs": attributes,
                                  "in_label": bool(self.label_stack)})
        if tag == "label":
            if attributes.get("for"):
                self.labels_for.add(attributes["for"])
            self.label_stack.append([])
        if tag == "button":
            self.buttons.append({"id": element_id, "attrs": attributes, "text": ""})
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.headings.append((int(tag[1]), ""))
        role = attributes.get("role")
        if role in {"tab", "tabpanel"}:
            entry = {"id": element_id, "attrs": attributes}
            (self.tabs if role == "tab" else self.tabpanels).append(entry)
        if tag not in VOID:
            self._stack.append((tag, attributes))

    def handle_data(self, data):
        text = data.strip()
        if not text:
            return
        if self.buttons:
            self.buttons[-1]["text"] += text + " "
        if self.headings and self._stack and self._stack[-1][0].startswith("h"):
            level, current = self.headings[-1]
            self.headings[-1] = (level, current + text + " ")

    def handle_endtag(self, tag):
        if tag == "label" and self.label_stack:
            self.label_stack.pop()
        if tag in VOID:
            return
        while self._stack:
            popped, _ = self._stack.pop()
            if popped == tag:
                break


def relative_luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    channels = [int(value[index:index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground: str, background: str) -> float:
    first, second = relative_luminance(foreground), relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def check_contrast(text: str, failures: list[str]) -> None:
    tokens: dict[str, str] = {}
    for block in re.finditer(r":root\s*\{([^}]*)\}", text):
        for match in re.finditer(r"--([a-z-]+):\s*(#[0-9a-fA-F]{6})", block.group(1)):
            tokens[match.group(1)] = match.group(2)
    dark_block = re.search(r"prefers-color-scheme:\s*dark\)\s*\{\s*:root\s*\{([^}]*)\}", text)
    dark = dict(tokens)
    if dark_block:
        for match in re.finditer(r"--([a-z-]+):\s*(#[0-9a-fA-F]{6})", dark_block.group(1)):
            dark[match.group(1)] = match.group(2)

    pairs = [
        ("fg", "bg", 4.5, "Text auf Seitenhintergrund"),
        ("fg", "card", 4.5, "Text auf Karte"),
        ("muted", "card", 4.5, "gedämpfter Text auf Karte"),
        ("muted", "bg", 4.5, "gedämpfter Text auf Seitenhintergrund"),
        ("accent", "bg", 4.5, "Link auf Seitenhintergrund"),
        ("accent", "card", 4.5, "Link auf Karte"),
        ("accent-fg", "accent", 4.5, "Text auf Aktionsknopf"),
        ("err", "card", 4.5, "Fehlermeldung auf Karte"),
        ("ok", "card", 3.0, "Statuspunkt (nicht-textlich)"),
        ("err", "bg", 3.0, "Statuspunkt auf Hintergrund"),
    ]
    for palette_name, palette in (("hell", tokens), ("dunkel", dark)):
        for foreground, background, minimum, label in pairs:
            if foreground not in palette or background not in palette:
                continue
            ratio = contrast(palette[foreground], palette[background])
            if ratio < minimum:
                failures.append(
                    f"Kontrast {palette_name}: {label} {palette[foreground]} auf {palette[background]} "
                    f"= {ratio:.2f}:1 (nötig {minimum}:1)"
                )


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    text = path.read_text(encoding="utf-8")
    ui = Ui()
    ui.feed(text)

    failures: list[str] = []
    checks: list[tuple[str, bool, str]] = []

    # Formulare: Label und zugänglicher Name
    unlabeled = [control["id"] or control["tag"] for control in ui.controls
                 if control["id"] not in ui.labels_for and not control["in_label"]]
    checks.append(("Jedes Eingabefeld hat ein Label", not unlabeled,
                   f"ohne Label: {', '.join(unlabeled)}"))

    # Buttons: zugänglicher Name
    nameless = [button["id"] or "(ohne id)" for button in ui.buttons
                if not button["text"].strip() and not button["attrs"].get("aria-label")]
    checks.append(("Jeder Knopf hat einen Namen", not nameless,
                   f"ohne Namen: {', '.join(nameless)}"))

    # ARIA-Verweise
    broken = [f"{key}={reference} (bei {owner})" for key, reference, owner in ui.aria_refs
              if reference not in ui.ids]
    checks.append(("ARIA-Verweise zeigen auf vorhandene IDs", not broken,
                   f"kaputt: {', '.join(broken)}"))

    # Tab-Muster
    selected = [tab for tab in ui.tabs if tab["attrs"].get("aria-selected") == "true"]
    focusable = [tab for tab in ui.tabs if str(tab["attrs"].get("tabindex", "0")) == "0"]
    tab_problems = []
    if len(ui.tabs) < 2:
        tab_problems.append("weniger als zwei Tabs")
    if len(selected) != 1:
        tab_problems.append(f"{len(selected)} Tabs mit aria-selected=true")
    if len(focusable) != 1:
        tab_problems.append(f"{len(focusable)} Tabs mit tabindex=0")
    for tab in ui.tabs:
        if tab["attrs"].get("aria-controls") not in ui.ids:
            tab_problems.append(f"Tab {tab['id']} ohne gültiges aria-controls")
    for panel in ui.tabpanels:
        if panel["attrs"].get("aria-labelledby") not in ui.ids:
            tab_problems.append(f"Panel {panel['id']} ohne gültiges aria-labelledby")
    checks.append(("Tab-Muster vollständig (tablist/tab/tabpanel)", not tab_problems,
                   "; ".join(tab_problems)))

    # Überschriften
    levels = [level for level, _ in ui.headings]
    heading_problems = []
    if levels.count(1) != 1:
        heading_problems.append(f"{levels.count(1)}× h1")
    for previous, current in zip(levels, levels[1:]):
        if current > previous + 1:
            heading_problems.append(f"Sprung von h{previous} auf h{current}")
    checks.append(("Überschriften ohne Sprünge, genau eine h1", not heading_problems,
                   "; ".join(heading_problems)))

    # Sprache und Zoom
    checks.append(("Sprachauszeichnung gesetzt", ui.html_lang.startswith("de"),
                   f"lang={ui.html_lang!r}"))
    zoom_blocked = "maximum-scale" in ui.viewport or "user-scalable=no" in ui.viewport
    checks.append(("Zoom nicht gesperrt", not zoom_blocked, ui.viewport))

    # Bedienziele und Fokus
    checks.append(("Bedienziel-Mindesthöhe gesetzt (--tap)", "--tap:" in text, "kein --tap-Token"))
    checks.append(("Sichtbarer Fokusstil vorhanden", ":focus-visible" in text, "kein :focus-visible"))
    checks.append(("Reduzierte Bewegung berücksichtigt", "prefers-reduced-motion" in text, "fehlt"))

    check_contrast(text, failures)

    print(f"Prüfe {path}")
    for label, ok, detail in checks:
        print(f"  [{'OK ' if ok else 'FEHL'}] {label}" + ("" if ok else f" – {detail}"))
        if not ok:
            failures.append(label)
    print("  [INFO] Kontrastprüfungen der Farb-Tokens: " +
          ("bestanden" if not failures else "siehe Fehler unten"))

    if failures:
        print("\nFehler:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nAlle Prüfungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
