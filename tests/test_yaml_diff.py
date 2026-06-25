"""
Unit tests for src/utils/yaml_diff.py.
"""

from src.utils.yaml_diff import flatten_dict, diff_dicts


def test_flatten_dict_simple():
    assert flatten_dict({"a": 1, "b": 2}) == {"a": 1, "b": 2}


def test_flatten_dict_nested():
    assert flatten_dict({"a": {"b": 1, "c": 2}}) == {"a.b": 1, "a.c": 2}


def test_flatten_dict_with_list():
    assert flatten_dict({"a": [10, 20, 30]}) == {"a[0]": 10, "a[1]": 20, "a[2]": 30}


def test_flatten_dict_nested_list_of_dicts():
    result = flatten_dict({"scenarios": [{"name": "a", "rate": 0.07}, {"name": "b", "rate": 0.08}]})
    assert result == {
        "scenarios[0].name": "a", "scenarios[0].rate": 0.07,
        "scenarios[1].name": "b", "scenarios[1].rate": 0.08,
    }


def test_diff_dicts_no_changes():
    d = {"a": 1, "b": {"c": 2}}
    assert diff_dicts(d, d) == []


def test_diff_dicts_simple_value_change():
    old = {"discount_rate": 0.07}
    new = {"discount_rate": 0.08}
    changes = diff_dicts(old, new)
    assert changes == [{"field": "discount_rate", "old_value": 0.07, "new_value": 0.08}]


def test_diff_dicts_nested_change():
    old = {"economics": {"discount_rate": 0.07, "years": 20}}
    new = {"economics": {"discount_rate": 0.08, "years": 20}}
    changes = diff_dicts(old, new)
    assert changes == [
        {"field": "economics.discount_rate", "old_value": 0.07, "new_value": 0.08}
    ]


def test_diff_dicts_multiple_changes_sorted_by_field():
    old = {"b": 1, "a": 1}
    new = {"b": 2, "a": 2}
    changes = diff_dicts(old, new)
    assert [c["field"] for c in changes] == ["a", "b"]


def test_diff_dicts_added_field():
    old = {"a": 1}
    new = {"a": 1, "b": 2}
    changes = diff_dicts(old, new)
    assert changes == [{"field": "b", "old_value": None, "new_value": 2}]


def test_diff_dicts_removed_field():
    old = {"a": 1, "b": 2}
    new = {"a": 1}
    changes = diff_dicts(old, new)
    assert changes == [{"field": "b", "old_value": 2, "new_value": None}]


def test_diff_dicts_list_element_change():
    old = {"pipe_cost_curve": [[0.0127, 5.0], [0.1016, 28.0]]}
    new = {"pipe_cost_curve": [[0.0127, 5.0], [0.1016, 30.0]]}
    changes = diff_dicts(old, new)
    assert changes == [{"field": "pipe_cost_curve[1][1]", "old_value": 28.0, "new_value": 30.0}]
