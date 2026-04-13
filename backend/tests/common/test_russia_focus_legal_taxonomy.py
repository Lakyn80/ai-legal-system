from __future__ import annotations

from app.modules.common.legal_taxonomy.russia_focus_taxonomy import RUSSIA_FOCUS_DATASET
from app.modules.common.legal_taxonomy.service import get_russia_focus_taxonomy_service


def test_dataset_scope_and_laws_present():
    law_ids = {l.law_id for l in RUSSIA_FOCUS_DATASET.laws}
    assert "local:ru/gpk" in law_ids
    assert "local:ru/sk" in law_ids
    assert "local:ru/echr" in law_ids
    assert "local:ru/fl115" in law_ids
    assert "local:ru/gk/1" not in law_ids  # intentionally excluded in this focused map


def test_issue_lookup_notice_returns_gpk_anchors():
    svc = get_russia_focus_taxonomy_service()
    rows = svc.get_articles_for_issue("notice_issue")
    keys = {(r.law_id, r.article_num) for r in rows}
    assert ("local:ru/gpk", "113") in keys
    assert ("local:ru/gpk", "116") in keys


def test_interpreter_topic_anchor_articles():
    svc = get_russia_focus_taxonomy_service()
    anchors = svc.get_anchor_articles_for_topic("interpreter_rights")
    keys = {(a.law_id, a.article_num) for a in anchors}
    assert ("local:ru/gpk", "9") in keys
    assert ("local:ru/gpk", "162") in keys


def test_alimony_law_priority_prefers_sk():
    svc = get_russia_focus_taxonomy_service()
    scores = svc.get_law_priority_for_topic("alimony")
    assert scores
    top_law = next(iter(scores.keys()))
    assert top_law == "local:ru/sk"


def test_reverse_maps_are_non_empty_for_active_scope():
    svc = get_russia_focus_taxonomy_service()
    topic_map = svc.get_topic_to_anchor_articles()
    issue_map = svc.get_issue_to_candidate_articles()
    assert "language_of_proceedings" in topic_map
    assert "interpreter_issue" in issue_map
    assert any(x.startswith("local:ru/gpk:") for x in issue_map["notice_issue"])


def test_enforcement_support_present_in_current_scope():
    svc = get_russia_focus_taxonomy_service()
    debt_rows = svc.get_articles_for_issue("alimony_debt_issue")
    keys = {(r.law_id, r.article_num) for r in debt_rows}
    assert ("local:ru/sk", "113") in keys
    assert ("local:ru/sk", "115") in keys
