import pytest

from app.advisor_tools import compute_delta, dispatch_tool


def test_compute_delta_only_changed_keys():
    before = {"TotalDPS": 100, "Life": 200, "Unchanged": "same"}
    after = {"TotalDPS": 150, "Life": 200, "Unchanged": "same"}
    delta = compute_delta(before, after)
    assert delta == {"TotalDPS": {"before": 100, "after": 150, "change": 50}}


def test_compute_delta_handles_new_and_missing_keys():
    before = {"A": 1}
    after = {"B": 2}
    delta = compute_delta(before, after)
    assert delta["A"]["after"] is None
    assert delta["B"]["before"] is None


def test_dispatch_tool_rejects_unknown_name():
    class _FakeSession:
        bridge = None

    with pytest.raises(ValueError):
        dispatch_tool(session=_FakeSession(), name="not_a_real_tool", tool_input={})
