"""Shared claim checker for model-written text.

Agents let the model write short prose (summaries, explanations, plan intros).
Before that prose reaches a user, it is scanned for factual claims:

- numbers with a temperature or percentage unit (44.2°C, 111 F, 21 %)
- phrases describing things no HeatWise tool returns (sky condition, rain) or
  official warnings when the provider does not publish them
- phone or emergency numbers (none was verified, so none may be stated).

Numbers must match a value from the evidence (within a tolerance); otherwise the
text is rejected by the caller and a deterministic text is used instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Literal

_NUMBER_RE = re.compile(
    r"(?<![\w.])(?P<num>-?\d+(?:\.\d+)?)\s*"
    r"(?P<unit>(?:°|º|˚)\s*[CF]\b|degrees?\s+(?:celsius|fahrenheit|[CF]\b)|[CF]\b|%|percent\b)",
    re.IGNORECASE,
)

# Phrases describing data no HeatWise tool returns. Always unsupported, negated or not.
_UNSUPPORTED_PHRASES = ("clear skies", "clear sky", "sunny skies", "rain expected", "expect rain", "rain is expected")
# Phrases naming official warnings. Unsupported when the provider has no alerts feed.
_ALERT_PHRASES = ("red alert", "orange alert", "yellow alert", "official warning", "official warnings",
                  "official alert", "official alerts", "heat wave warning", "heatwave warning")
# Phone or emergency numbers. HeatWise verified no emergency number (see guidance/sources.py),
# so any number a model writes next to call/dial/helpline, or any phone-shaped digit run, is rejected.
_UNIT_AHEAD = r"(?!\d)(?!\s*(?:°|º|˚|%|degrees?\b|percent\b|[CF]\b))"
PHONE_NUMBER_RE = re.compile(
    r"\b(?:call(?:ing)?|dial(?:l?ing)?|phone|ring|text|sms|whatsapp|helpline|hotline|toll[\s-]?free|number"
    r"|contact|reach|ambulance|emergency|police|fire|rescue|control\s+room)\b"
    rf"[^.!?\n\d]{{0,25}}?\+?\d(?:[\s-]?\d){{2,}}{_UNIT_AHEAD}"
    r"|\+\d{1,3}[\s-]?\d(?:[\s-]?\d){5,}"
    r"|(?<![\w.])\d(?:[\s-]?\d){6,}(?![\w.])"
    rf"|\b9-1-1\b|(?<![\d.])\b(?:911|112|108)\b(?!\.\d){_UNIT_AHEAD}",
    re.IGNORECASE,
)
_NEGATIONS = re.compile(r"\b(no|not|never|without|none|unavailable|isn't|aren't|cannot|can't)\b", re.IGNORECASE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class Claim:
    kind: Literal["number", "phrase"]
    text: str
    value: float | None = None
    unit: Literal["C", "F", "%"] | None = None
    negated: bool = False


def _unit(raw: str) -> Literal["C", "F", "%"]:
    r = raw.lower()
    if "%" in r or "percent" in r:
        return "%"
    if r.rstrip().endswith("f") or "fahrenheit" in r:
        return "F"
    return "C"


def extract_claims(text: str | None) -> list[Claim]:
    """Return numeric claims (with unit) and notable phrases found in `text`."""
    if not text:
        return []
    claims: list[Claim] = []
    for m in _NUMBER_RE.finditer(text):
        claims.append(Claim(kind="number", text=m.group(0), value=float(m.group("num")), unit=_unit(m.group("unit"))))
    for sentence in _SENTENCE_SPLIT.split(text):
        low = sentence.lower()
        negated = bool(_NEGATIONS.search(sentence))
        for phrase in (*_UNSUPPORTED_PHRASES, *_ALERT_PHRASES):
            # Word boundaries keep "official warning" from matching inside "official warnings".
            if re.search(rf"\b{re.escape(phrase)}\b", low):
                claims.append(Claim(kind="phrase", text=phrase, negated=negated))
    return claims


def check_text_claims(
    text: str | None,
    allowed_numbers: Iterable[float],
    alerts_supported: bool,
    tolerance: float = 0.5,
) -> list[str]:
    """Return a list of problems; an empty list means the text makes no unsupported claim.

    `allowed_numbers` are the values present in the evidence (include both °C and
    °F forms where the text may use either).
    """
    allowed = [float(x) for x in allowed_numbers if x is not None]
    problems: list[str] = []
    for c in extract_claims(text):
        if c.kind == "number":
            if not any(abs(c.value - a) <= tolerance for a in allowed):  # type: ignore[operator]
                problems.append(f"Unsupported value '{c.text}' is not in the evidence.")
        elif c.text in _UNSUPPORTED_PHRASES:
            # Flagged even when negated ("no rain expected" is still a sky/rain claim).
            problems.append(f"Unsupported claim '{c.text}': no tool returns this information.")
        elif not alerts_supported and not c.negated:
            problems.append(f"Unsupported claim '{c.text}': the provider does not publish official warnings.")
    for m in PHONE_NUMBER_RE.finditer(text or ""):
        problems.append(f"Phone or emergency number '{m.group(0).strip()}' is not allowed; "
                        "no emergency number was verified.")
    return problems
