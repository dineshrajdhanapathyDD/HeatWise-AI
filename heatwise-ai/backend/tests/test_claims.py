"""Shared claim checker tests."""

from __future__ import annotations

from backend.services.claims import check_text_claims, extract_claims


def test_extracts_numbers_with_units():
    claims = extract_claims("It is 44.2°C (111.6 °F), humidity 21%, and 46 C later; 3 days, 2 groups.")
    nums = [(c.value, c.unit) for c in claims if c.kind == "number"]
    assert nums == [(44.2, "C"), (111.6, "F"), (21.0, "%"), (46.0, "C")]


def test_unitless_and_word_numbers_are_ignored():
    assert [c for c in extract_claims("Check on 2 neighbours for 3 days. Version 1.5 Fields.") if c.kind == "number"] == []


def test_numbers_within_tolerance_pass():
    assert check_text_claims("About 44°C and 21% humidity.", {44.2, 21.0}, alerts_supported=False) == []


def test_unsupported_number_flagged():
    problems = check_text_claims("Temperatures near 30°C.", {44.2}, alerts_supported=False)
    assert len(problems) == 1 and "30°C" in problems[0]


def test_unsupported_phrases_flagged_even_when_negated():
    problems = check_text_claims("Clear skies today. No rain expected.", set(), alerts_supported=True)
    assert len(problems) == 2


def test_alert_phrases_depend_on_provider_support():
    text = "An orange alert is in force with an official warning."
    assert len(check_text_claims(text, set(), alerts_supported=False)) == 2
    assert check_text_claims(text, set(), alerts_supported=True) == []


def test_negated_alert_statement_is_allowed():
    text = "No official warnings are available from this provider. Forecast values are not official warnings."
    assert check_text_claims(text, set(), alerts_supported=False) == []


def test_phone_and_emergency_numbers_flagged():
    for bad in ("If someone collapses, call 108 for an ambulance.", "Dial 112 or 911 right away.",
                "Call the helpline at +91 98765 43210.", "Ring 9-1-1.", "Helpline: 1800 180 1104."):
        problems = check_text_claims(bad, set(), alerts_supported=False)
        assert any("Phone or emergency number" in p for p in problems), bad


def test_keywordless_short_emergency_codes_flagged():
    # Review pass 3 gap: short service numbers next to an emergency word, without call/dial.
    for bad in ("Ambulance: 102.", "Emergency services (102) can help.", "Police 100 and fire 101 are available.",
                "Contact the disaster control room on 1070."):
        problems = check_text_claims(bad, set(), alerts_supported=False)
        assert any("Phone or emergency number" in p for p in problems), bad


def test_ordinary_counts_are_not_phone_numbers():
    text = "Check on 100 households. Keep water within 100 metres. In an emergency, contact local services."
    assert check_text_claims(text, {100.0}, alerts_supported=False) == []


def test_temperatures_are_not_phone_numbers():
    text = "The heat index is about 108°F (42.2°C); highs of 112 F are possible. Call a neighbour twice a day."
    assert check_text_claims(text, {108.0, 42.2, 112.0}, alerts_supported=False) == []


def test_empty_text():
    assert extract_claims(None) == [] and check_text_claims("", set(), False) == []
