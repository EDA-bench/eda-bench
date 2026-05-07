from harnesses import utils as harness_utils


def test_builtin_matrix_has_requested_configs() -> None:
    matrix = harness_utils.builtin_harness_matrix()
    assert ("codex", "gpt-5.5", "web", "low") in matrix
    assert ("codex", "gpt-5.5", "web", "medium") in matrix
    assert ("codex", "gpt-5.5", "web", "high") in matrix
    assert ("codex", "gpt-5.5", "web", "xhigh") in matrix
    assert ("codex", "gpt-5.5", "no_web", "medium") in matrix
    assert ("pi", "gemini-3.1-pro-preview", "web", "high") in matrix
    assert ("pi", "deepseek/deepseek-v4-pro", "web", "high") in matrix
