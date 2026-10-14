import hashlib
import pytest

from tongyun_learn.services.cardkeys import front_key, normalize_front


@pytest.mark.parametrize(
    ("input_val", "expected"),
    [
        ("hello", "hello"),
        ("Hello", "hello"),
        ("  Hello World  ", "hello world"),
        ("hello\t\n  world", "hello world"),
        ("multiple   spaces   between", "multiple spaces between"),
        ("", ""),
        ("   ", ""),
        (None, ""),
        ("Ｈｅｌｌｏ", "hello"),  # 全角英文字符 NFKC
        ("１２３", "123"),  # 全角数字
        ("hello\u3000world", "hello world"),  # 全角空格
        ("STRAßE", "strasse"),  # casefold 特性
    ],
)
def test_normalize_front(input_val, expected):
    assert normalize_front(input_val) == expected


def test_front_key_format():
    key = front_key("abandon")
    assert isinstance(key, str)
    assert len(key) == 64
    assert all(c in "0123456789abcdef" for c in key)
    assert key == hashlib.sha256(b"abandon").hexdigest()


def test_front_key_equivalence():
    # 大小写、多余空白、全角字符应映射到相同 front_key
    k1 = front_key("Apple")
    k2 = front_key("  apple  ")
    k3 = front_key("APPLE")
    k4 = front_key("Ａｐｐｌｅ")
    assert k1 == k2 == k3 == k4


def test_front_key_distinct():
    assert front_key("abandon") != front_key("ability")
    assert front_key("cat") != front_key("dog")


def test_front_key_empty():
    empty_sha256 = hashlib.sha256(b"").hexdigest()
    assert front_key("") == empty_sha256
    assert front_key("   ") == empty_sha256
    assert front_key(None) == empty_sha256
