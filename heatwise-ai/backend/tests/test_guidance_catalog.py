"""Guidance catalog, sources and SKILL.md checks."""

from __future__ import annotations

from pathlib import Path

import pytest
from strands import Skill

from backend.agents.planner_agent import AUDIENCE_SKILLS, SKILLS_DIR
from backend.guidance.catalog import AUDIENCES, CATALOG, PHASES, REQUIRED_TOPICS, catalog_for
from backend.guidance.sources import TRUSTED_SOURCES
from backend.tools.verification_tools import banned_hits


def test_every_source_id_exists():
    for item in CATALOG.values():
        assert item.source_ids, item.id
        for sid in item.source_ids:
            assert sid in TRUSTED_SOURCES, (item.id, sid)


def test_all_source_urls_are_https():
    for s in TRUSTED_SOURCES.values():
        assert s.url.startswith("https://"), s.id


@pytest.mark.parametrize("audience", AUDIENCES)
@pytest.mark.parametrize("phase", PHASES)
def test_every_audience_phase_non_empty_at_lowest_category(audience, phase):
    assert catalog_for(audience, phase, "low")


@pytest.mark.parametrize("audience", AUDIENCES)
def test_required_topics_per_audience(audience):
    topics = {i.topic for i in catalog_for(audience, None, "low")}
    assert set(REQUIRED_TOPICS) <= topics


def test_items_are_short_paraphrases_without_banned_content_or_numbers():
    for item in CATALOG.values():
        assert len(item.text.split()) <= 45, item.id
        assert banned_hits(item.text) == [], item.id
        assert "112" not in item.text and "911" not in item.text and "9-1-1" not in item.text


def test_category_filter():
    low = {i.id for i in catalog_for("outdoor_worker", "during", "low")}
    extreme = {i.id for i in catalog_for("outdoor_worker", "during", "extreme")}
    assert "ow-during-work_schedule-1" not in low and "ow-during-work_schedule-1" in extreme
    assert low < extreme


def test_skill_dirs_load_with_matching_names():
    dirs = sorted(p for p in Path(SKILLS_DIR).iterdir() if p.is_dir())
    assert {d.name for d in dirs} == set(AUDIENCE_SKILLS.values())
    for d in dirs:
        skill = Skill.from_file(d, strict=True)
        assert skill.name == d.name
        assert skill.description
        assert "list_guidance" in skill.instructions and "select_guidance" in skill.instructions
        assert "add_general_advice" in skill.instructions
