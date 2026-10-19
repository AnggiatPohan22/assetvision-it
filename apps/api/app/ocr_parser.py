"""Conservative label parser; never repair ambiguous characters or infer physical identity."""

import re

from app.identifier_values import IdentifierType, normalize_identifier
from app.ocr_schemas import IdentifierCandidate, OCRLine

# Labels delimit values on the same line. No fuzzy matching of label text or O/0, I/1 swaps.
LABEL = re.compile(
    r"(?<![A-Za-z0-9])(?P<label>serial(?:\s+(?:number|no\.?))?|s\s*/\s*n|s/n|sn|"
    r"(?:lan|wlan|wi-fi|wifi)\s+mac(?:\s+address)?|bssid|mac(?:\s+address)?|"
    r"model(?:\s+(?:number|no\.?))?)(?=$|[\s:=#])\s*(?:[:=]|#)?\s*",
    re.IGNORECASE,
)
MAC_VALUE = re.compile(
    r"(?:[0-9A-Fa-f]{12}|(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}|"
    r"(?:[0-9A-Fa-f]{2}-){5}[0-9A-Fa-f]{2}|(?:[0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4})"
)


def parse_lines(
    lines: tuple[OCRLine, ...], *, manual: bool = False
) -> tuple[IdentifierCandidate, ...]:
    candidates: list[IdentifierCandidate] = []
    for index, line in enumerate(lines):
        matches = list(LABEL.finditer(line.text))
        for offset, match in enumerate(matches):
            end = matches[offset + 1].start() if offset + 1 < len(matches) else len(line.text)
            raw = line.text[match.end() : end].strip()
            indices = (index,)
            scores = [line.score]
            # A standalone label can precede its value. Do not consume another labelled field.
            if not raw and len(matches) == 1 and index + 1 < len(lines):
                following = lines[index + 1]
                if not LABEL.search(following.text):
                    raw = following.text.strip()
                    indices = (index, index + 1)
                    scores.append(following.score)
            label = re.sub(r"\s+", " ", match["label"].lower())
            kind = (
                "MAC_LAN"
                if label.startswith("lan ")
                else "MAC_WLAN"
                if label.startswith(("wlan ", "wi-fi ", "wifi "))
                else "BSSID"
                if label == "bssid"
                else "MAC"
                if label.startswith("mac")
                else "MODEL"
                if label.startswith("model")
                else "SERIAL_NUMBER"
            )
            if not raw or len(raw) > 255:
                continue
            issues = []
            if not manual and min(scores) < 0.85:
                issues.append("LOW_OCR_SCORE")
            if kind in {"MAC", "MAC_LAN", "MAC_WLAN", "BSSID"}:
                if MAC_VALUE.fullmatch(raw) is None:
                    continue
                normalized = normalize_identifier(IdentifierType.MAC_LAN, raw)
                if kind == "MAC":
                    issues.append("MAC_TYPE_UNSPECIFIED")
                compact = normalized.replace(":", "")
                if compact in {"0" * 12, "F" * 12} or int(compact[:2], 16) & 1:
                    issues.append("NON_DEVICE_MAC_ADDRESS")
            else:
                # Spaces inside identifiers and damage markers require explicit human entry.
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/\-]{0,254}", raw):
                    continue
                try:
                    normalized = normalize_identifier(IdentifierType.SERIAL_NUMBER, raw)
                except ValueError:
                    continue
                if not manual and re.search(r"[O0Il1]", raw):
                    issues.append("CHECK_AMBIGUOUS_CHARACTERS")
            candidates.append(
                IdentifierCandidate(
                    kind=kind,
                    raw_value=raw,
                    normalized_value=normalized,
                    source="MANUAL" if manual else "OCR",
                    line_indices=indices,
                    issues=tuple(issues),
                )
            )
    # Multiple claims remain separate evidence, including conflicting values on one label.
    return tuple(candidates)
