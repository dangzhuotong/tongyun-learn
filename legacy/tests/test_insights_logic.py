import pytest

from tongyun_learn.errors import ApiError
from tongyun_learn.services.insights import parse_days


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1,3,7", [1, 3, 7]),
        (" 7 , 1 , 3 ", [1, 3, 7]),
        ("1,1,3,7,7", [1, 3, 7]),  # 去重并排序
        ("1", [1]),
        ("365", [365]),
        ("10, 20, 30", [10, 20, 30]),
    ],
)
def test_parse_days_valid(raw, expected):
    assert parse_days(raw) == expected


@pytest.mark.parametrize(
    "invalid_input",
    [
        "",  # 空串
        "   ",  # 空白
        ",,,",  # 仅逗号
        "abc",  # 非数字
        "1,abc,3",  # 部分非数字
        "0",  # 小于 1
        "366",  # 大于 365
        "-5",  # 负数
        "1,2,3,4,5,6,7,8,9,10,11",  # 超过 10 个
    ],
)
def test_parse_days_invalid(invalid_input):
    with pytest.raises(ApiError) as exc_info:
        parse_days(invalid_input)
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "invalid_days"
