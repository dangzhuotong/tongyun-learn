import pytest

from tongyun_learn.errors import ApiError
from tongyun_learn.services.tutor import (
    EXPRESS_PASS,
    SELFTEST_PASS,
    express_to_rating,
    judge_passed,
)


@pytest.mark.parametrize(
    ("score", "max_score", "expected"),
    [
        (4.0, 5.0, True),  # 4/5 = 0.8 -> pass
        (3.99, 5.0, False),  # 3.99/5 = 0.798 < 0.8 -> fail
        (5.0, 5.0, True),  # 1.0 -> pass
        (0.0, 5.0, False),  # 0.0 -> fail
        (8.0, 10.0, True),  # 0.8 -> pass
    ],
)
def test_judge_passed_selftest(score, max_score, expected):
    assert judge_passed("selftest", score=score, max_score=max_score, passed=None) is expected


@pytest.mark.parametrize(
    ("score", "max_score", "expected"),
    [
        (6.0, 8.0, True),  # 6/8 = 0.75 -> pass
        (5.9, 8.0, False),  # 5.9/8 = 0.7375 < 0.75 -> fail
        (8.0, 8.0, True),  # 1.0 -> pass
        (0.0, 8.0, False),  # 0.0 -> fail
        (7.5, 10.0, True),  # 0.75 -> pass
    ],
)
def test_judge_passed_express(score, max_score, expected):
    assert judge_passed("express", score=score, max_score=max_score, passed=None) is expected


@pytest.mark.parametrize(
    ("type_", "score", "max_score"),
    [
        ("selftest", None, 5.0),
        ("selftest", 4.0, None),
        ("selftest", 4.0, 0.0),
        ("selftest", -1.0, 5.0),
        ("selftest", 6.0, 5.0),
        ("express", None, 8.0),
        ("express", 6.0, None),
        ("express", 6.0, 0.0),
        ("express", -0.1, 8.0),
        ("express", 8.5, 8.0),
    ],
)
def test_judge_passed_scored_validation_errors(type_, score, max_score):
    with pytest.raises(ApiError) as exc_info:
        judge_passed(type_, score=score, max_score=max_score, passed=None)
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "validation_error"


@pytest.mark.parametrize(
    ("type_", "passed", "expected"),
    [
        ("feynman", True, True),
        ("feynman", False, False),
        ("handson", True, True),
        ("handson", False, False),
    ],
)
def test_judge_passed_boolean_types(type_, passed, expected):
    assert judge_passed(type_, score=None, max_score=None, passed=passed) is expected


@pytest.mark.parametrize("type_", ["feynman", "handson"])
def test_judge_passed_boolean_missing_passed_error(type_):
    with pytest.raises(ApiError) as exc_info:
        judge_passed(type_, score=None, max_score=None, passed=None)
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "validation_error"


def test_express_to_rating_boundaries():
    # 比例 < 0.5 -> 1 (Again)
    assert express_to_rating(0.0, 8.0) == 1
    assert express_to_rating(3.9, 8.0) == 1

    # 0.5 <= 比例 < 0.75 -> 2 (Hard)
    assert express_to_rating(4.0, 8.0) == 2
    assert express_to_rating(5.99, 8.0) == 2

    # 0.75 <= 比例 < 1.0 -> 3 (Good)
    assert express_to_rating(6.0, 8.0) == 3
    assert express_to_rating(7.99, 8.0) == 3

    # 比例 == 1.0 -> 4 (Easy)
    assert express_to_rating(8.0, 8.0) == 4
    assert express_to_rating(10.0, 10.0) == 4

    # max_score 为 0 时容错返回 1
    assert express_to_rating(5.0, 0.0) == 1
