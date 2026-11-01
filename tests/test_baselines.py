from dataclasses import asdict
import json

from evaluation import baselines
from control.skill_schema import LIMITS, load_skill


def test_random_samples_are_reproducible_valid_and_independent():
    first = baselines.sample_skills(42)
    assert first == baselines.sample_skills(42)
    assert first != baselines.sample_skills(43)
    assert [s.version for s in first] == [2, 3, 4]
    for skill in first:
        for field, (low, high) in LIMITS.items():
            assert low <= getattr(skill, field) <= high


def test_search_uses_exactly_four_evaluations_and_rejects_success_regression(tmp_path, monkeypatch):
    calls = []

    def fake_evaluate(path, output):
        # Candidate 1 has a bigger scalar score but fewer successes: must reject.
        metrics = [([.5, -.1, -1], 50), ([.4, -.01, -1], 60),
                   ([.6, -.1, -1], 65), ([.6, -.2, -1], 70)]
        rank, score = metrics[len(calls)]
        calls.append(load_skill(path))
        return {"skill_sha256": "fixture", "aggregate": {
            "eligible": True, "rank": rank, "score": score, "successes": int(rank[0] * 15)}}

    monkeypatch.setattr(baselines, "evaluate", fake_evaluate)
    report = baselines.run_search(tmp_path / "search")
    assert len(calls) == 4
    assert report["selected"] == "random_2"
    assert report["improved_over_initial"]
    manifest = json.loads((tmp_path / "search/manifest.json").read_text())
    assert len(manifest["sampled_skills"]) == 3
    assert report["kind"] == "conventional_random_search_not_agent_authored"
