from simulation.smoke import run_episode


def test_seeded_episode_is_reproducible(tmp_path):
    first = run_episode(42, tmp_path / "first")
    second = run_episode(42, tmp_path / "second")
    assert first["trajectory_sha256"] == second["trajectory_sha256"]
    assert first["observation_shape"] == [23]
    assert first["action_shape"] == [7]
    assert first["steps"] == 100
    assert first["truncated"]
