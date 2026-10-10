"""Parse the Markdown body that GitHub generates from an issue form.

GitHub renders every form field as ``### <label>`` followed by the answer.
Labels are mapped back to field ids using the form definition itself, so the
template in ``.github/ISSUE_TEMPLATE`` stays the single source of truth.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from common import load_yaml

NO_RESPONSE = "_No response_"
CHECKBOX_RE = re.compile(r"^- \[([ xX])\] (.+)$")


@dataclass
class FormField:
    id: str
    label: str
    type: str
    options: list[str]


def form_fields(template: Path) -> list[FormField]:
    spec = load_yaml(template) or {}
    fields = []
    for item in spec.get("body", []):
        if item.get("type") == "markdown" or "id" not in item:
            continue
        attrs = item.get("attributes", {})
        options = [o["label"] if isinstance(o, dict) else o for o in attrs.get("options", [])]
        fields.append(FormField(id=item["id"], label=attrs["label"], type=item["type"], options=options))
    return fields


def parse(body: str, template: Path) -> dict[str, object]:
    """Return {field id: value}. Checkboxes map to {option label: checked}."""
    fields = form_fields(template)
    order = {f.label: i for i, f in enumerate(fields)}
    sections: dict[str, list[str]] = {}
    current, position = None, -1
    for line in (body or "").replace("\r\n", "\n").split("\n"):
        heading = re.match(r"^### (.+?)\s*$", line)
        # Headings are accepted once and only in template order, so a `### Label`
        # line typed inside an answer cannot overwrite an earlier field.
        if heading and order.get(heading.group(1), -1) > position:
            current, position = heading.group(1), order[heading.group(1)]
            sections[current] = []
        elif current is not None:
            sections[current].append(line)

    values: dict[str, object] = {}
    for f in fields:
        raw = "\n".join(sections.get(f.label, [])).strip()
        if raw == NO_RESPONSE:
            raw = ""
        if f.type == "checkboxes":
            checked = {}
            for line in raw.split("\n"):
                m = CHECKBOX_RE.match(line.strip())
                if m:
                    checked[m.group(2).strip()] = m.group(1).lower() == "x"
            values[f.id] = {opt: checked.get(opt, False) for opt in f.options}
        else:
            values[f.id] = raw
    return values
