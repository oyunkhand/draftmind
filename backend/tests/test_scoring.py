import math

from app.engine import scoring
from app.engine.draft import DraftState
from app.engine.explain import template_explanation
from app.engine.stats import smoothed


def test_softmax_is_a_distribution():
    p = scoring.softmax([1.0, 2.0, 3.0], 0.5)
    assert math.isclose(sum(p), 1.0)
    assert p[2] > p[1] > p[0]
    assert scoring.softmax([], 1.0) == []


def test_smoothing_pulls_small_samples_to_prior():
    assert smoothed(1, 1) < 0.6
    assert smoothed(70, 100) > 0.68


def test_comfort_and_recency(mini_index):
    cf = mini_index.comfort("BBB-mid", "Orianna")
    assert cf["games"] == 9 and cf["score"] > 0.7
    assert mini_index.comfort("BBB-mid", "Azir")["score"] == 0.0


def test_prediction_favours_opponent_comfort_and_sums_to_at_most_one(mini_index):
    st = DraftState("AAA", "BBB")
    for c in ["Teemo", "Shaco", "Singed", "Heimerdinger", "Rammus", "Nunu", "Vi"]:
        st.apply(c)
    pred = scoring.predict_opponent(mini_index, st, "red", top=200)
    probs = [p["probability"] for p in pred["predictions"]]
    assert pred["step"]["label"] == "R1 pick"
    assert probs == sorted(probs, reverse=True)
    assert sum(probs) <= 1.0001
    top5 = [p["champion"] for p in pred["predictions"][:5]]
    assert set(top5) & {"Orianna", "Sejuani", "Kaisa", "Nautilus", "Renekton"}
    assert "Vi" not in [p["champion"] for p in pred["predictions"]]  # taken champions are never predicted
    assert all(p["factors"] and p["why"] for p in pred["predictions"][:5])


def test_recommendation_respects_roles_and_availability(mini_index):
    st = DraftState("AAA", "BBB", fearless_mode="hard", locked={"blue": ["Azir"], "red": ["Azir"]})
    for c in ["Teemo", "Shaco", "Singed", "Heimerdinger", "Rammus", "Nunu"]:
        st.apply(c)
    rec = scoring.recommend(mini_index, st, "blue")
    names = [r["champion"] for r in rec["recommendations"]]
    assert rec["type"] == "pick" and len(names) == 8
    assert "Azir" not in names  # fearless-locked
    assert all(0 <= r["score"] <= 100 for r in rec["recommendations"])
    totals = [r["total"] for r in rec["recommendations"]]
    assert totals == sorted(totals, reverse=True)
    # Explainability: the total is exactly the sum of factor contributions.
    r0 = rec["recommendations"][0]
    assert math.isclose(r0["total"], sum(f["contribution"] for f in r0["factors"]), abs_tol=1e-3)
    assert {f["key"] for f in r0["factors"]} == set(scoring.PICK_FACTORS)


def test_counter_factor_uses_matchup_data(mini_index):
    st = DraftState("AAA", "BBB")
    for c in ["Teemo", "Shaco", "Singed", "Heimerdinger", "Rammus", "Nunu", "Vi", "Renekton"]:
        st.apply(c)
    v, det = scoring.counter_value(mini_index, "Jayce", "top", {"top": "Renekton"})
    assert v > 0.5 and det[0]["enemy"] == "Renekton" and det[0]["lane"]
    v2, _ = scoring.counter_value(mini_index, "Renekton", "top", {"top": "Jayce"})
    assert v2 < 0


def test_weights_change_ranking(mini_index):
    st = DraftState("AAA", "BBB")
    for c in ["Teemo", "Shaco", "Singed", "Heimerdinger", "Rammus", "Nunu"]:
        st.apply(c)
    comfort_only = {"pick": {k: 0.0 for k in scoring.PICK_FACTORS}}
    comfort_only["pick"]["comfort"] = 1.0
    rec = scoring.recommend(mini_index, st, "blue", weights=comfort_only)
    assert rec["recommendations"][0]["champion"] in {"Gnar", "Vi", "Azir", "Varus", "Rakan"}
    deny_only = {"pick": {k: 0.0 for k in scoring.PICK_FACTORS}}
    deny_only["pick"]["deny"] = 1.0
    rec2 = scoring.recommend(mini_index, st, "blue", weights=deny_only)
    assert rec2["recommendations"][0]["champion"] in {"Renekton", "Sejuani", "Orianna", "Kaisa", "Nautilus"}


def test_ban_recommendation_targets_opponent_comfort(mini_index):
    st = DraftState("AAA", "BBB")
    rec = scoring.recommend(mini_index, st, "blue")
    assert rec["type"] == "ban"
    top3 = [r["champion"] for r in rec["recommendations"][:3]]
    assert set(top3) <= {"Renekton", "Sejuani", "Orianna", "Kaisa", "Nautilus"}
    assert {f["key"] for f in rec["recommendations"][0]["factors"]} == set(scoring.BAN_FACTORS)


def test_exclude_removes_rejected_champions(mini_index):
    st = DraftState("AAA", "BBB")
    first = scoring.recommend(mini_index, st, "blue")["recommendations"][0]["champion"]
    again = scoring.recommend(mini_index, st, "blue", exclude={first})["recommendations"]
    assert first not in [r["champion"] for r in again]


def test_coach_affinity_from_decisions():
    log = [
        {"action_type": "pick", "decision": "accept", "suggested_champion": "Vi", "final_champion": "Vi"},
        {"action_type": "pick", "decision": "accept", "suggested_champion": "Vi", "final_champion": "Vi"},
        {"action_type": "pick", "decision": "reject", "suggested_champion": "Jinx", "final_champion": None},
        {"action_type": "pick", "decision": "modify", "suggested_champion": "Ahri", "final_champion": "Azir"},
        {"action_type": "ban", "decision": "accept", "suggested_champion": "Kalista", "final_champion": "Kalista"},
    ]
    aff = scoring.coach_affinity(log)
    assert aff["pick"]["Vi"]["value"] > aff["pick"]["Azir"]["value"] > 0
    assert aff["pick"]["Jinx"]["value"] < aff["pick"]["Ahri"]["value"] < 0
    assert aff["pick"]["Vi"]["accepted"] == 2
    assert "Kalista" in aff["ban"] and "Kalista" not in aff["pick"]


def test_coach_affinity_moves_recommendations(mini_index):
    st = DraftState("AAA", "BBB")
    for c in ["Teemo", "Shaco", "Singed", "Heimerdinger", "Rammus", "Nunu"]:
        st.apply(c)
    base = scoring.recommend(mini_index, st, "blue", top=30)["recommendations"]
    target = base[5]["champion"]
    aff = scoring.coach_affinity([{"action_type": "pick", "decision": "accept", "suggested_champion": target}] * 4)
    boosted = scoring.recommend(mini_index, st, "blue", coach_affinity=aff, top=30)["recommendations"]
    total = lambda lst: next(r["total"] for r in lst if r["champion"] == target)  # noqa: E731
    rank = lambda lst: [r["champion"] for r in lst].index(target)  # noqa: E731
    expected = scoring.DEFAULT_WEIGHTS["pick"]["coach"] * aff["pick"][target]["value"]
    assert math.isclose(total(boosted) - total(base), expected, abs_tol=1e-3)
    assert rank(boosted) <= rank(base)
    strong = scoring.recommend(mini_index, st, "blue", weights={"pick": {"coach": 5.0}}, coach_affinity=aff,
                               top=30)["recommendations"]
    assert rank(strong) < rank(base)


def test_merge_weights_clamps_and_ignores_unknown():
    w = scoring.merge_weights({"pick": {"meta": 99, "bogus": 1}, "ban": {"threat": -3}})
    assert w["pick"]["meta"] == 5.0 and "bogus" not in w["pick"]
    assert w["ban"]["threat"] == 0.0
    assert w["pick"]["counter"] == scoring.DEFAULT_WEIGHTS["pick"]["counter"]


def test_template_explanation_cites_evidence(mini_index):
    st = DraftState("AAA", "BBB")
    rec = scoring.recommend(mini_index, st, "blue")["recommendations"][0]
    text = template_explanation(rec)
    assert rec["name"] in text and rec["factors"][0]["evidence"] in text


def test_sample_dataset_has_required_volume(sample_index):
    assert len(sample_index.teams) >= 6
    assert sample_index.total_games >= 60
    assert all(len(m["draft"]) == 20 for m in sample_index.matches)
