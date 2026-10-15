import json
import pytest
from pydantic import ValidationError

from tongyun_learn.ai.schemas import validate
from tongyun_learn.ai.service import canonical_input
from tongyun_learn.errors import ApiError
from tongyun_learn.routers.ai import QuizRequest, QuizWordItem
from tongyun_learn.services.tutor import (
    EXPRESS_PASS,
    SELFTEST_PASS,
    express_to_rating,
    judge_passed,
)


def test_judge_passed_selftest_precise_threshold():
    assert SELFTEST_PASS == 0.8
    # Exact pass threshold
    assert judge_passed("selftest", score=8.0, max_score=10.0, passed=None) is True
    assert judge_passed("selftest", score=4.0, max_score=5.0, passed=None) is True

    # Just below threshold -> fail
    assert judge_passed("selftest", score=7.99, max_score=10.0, passed=None) is False
    assert judge_passed("selftest", score=3.99, max_score=5.0, passed=None) is False

    # Extreme bounds
    assert judge_passed("selftest", score=10.0, max_score=10.0, passed=None) is True
    assert judge_passed("selftest", score=0.0, max_score=10.0, passed=None) is False


def test_judge_passed_express_precise_threshold():
    assert EXPRESS_PASS == 0.75
    # Exact pass threshold
    assert judge_passed("express", score=3.0, max_score=4.0, passed=None) is True
    assert judge_passed("express", score=7.5, max_score=10.0, passed=None) is True

    # Just below threshold -> fail
    assert judge_passed("express", score=2.99, max_score=4.0, passed=None) is False
    assert judge_passed("express", score=7.49, max_score=10.0, passed=None) is False

    # Extreme bounds
    assert judge_passed("express", score=4.0, max_score=4.0, passed=None) is True
    assert judge_passed("express", score=0.0, max_score=4.0, passed=None) is False


def test_judge_passed_score_validation_bounds():
    # Negative score
    with pytest.raises(ApiError) as exc:
        judge_passed("selftest", score=-0.01, max_score=10.0, passed=None)
    assert exc.value.status_code == 422
    assert exc.value.code == "validation_error"

    # Score exceeding max_score
    with pytest.raises(ApiError) as exc:
        judge_passed("express", score=10.5, max_score=10.0, passed=None)
    assert exc.value.status_code == 422

    # Zero or negative max_score
    with pytest.raises(ApiError) as exc:
        judge_passed("selftest", score=0.0, max_score=0.0, passed=None)
    assert exc.value.status_code == 422

    with pytest.raises(ApiError) as exc:
        judge_passed("express", score=1.0, max_score=-5.0, passed=None)
    assert exc.value.status_code == 422


def test_express_to_rating_all_tiers():
    max_score = 10.0

    # Tier 1 (Again, rating=1): ratio < 0.5
    assert express_to_rating(0.0, max_score) == 1
    assert express_to_rating(4.99, max_score) == 1

    # Tier 2 (Hard, rating=2): 0.5 <= ratio < 0.75
    assert express_to_rating(5.0, max_score) == 2
    assert express_to_rating(7.49, max_score) == 2

    # Tier 3 (Good, rating=3): 0.75 <= ratio < 1.0
    assert express_to_rating(7.5, max_score) == 3
    assert express_to_rating(9.99, max_score) == 3

    # Tier 4 (Easy, rating=4): ratio >= 1.0
    assert express_to_rating(10.0, max_score) == 4
    assert express_to_rating(12.0, max_score) == 4

    # Graceful handling when max_score is 0
    assert express_to_rating(10.0, 0.0) == 1


def test_validate_word_quiz_choice_rules():
    # Valid 4 options with answer inside
    valid_choice = {
        "questions": [
            {
                "type": "choice",
                "word": "concurrency",
                "stem": "Which term describes overlapping executions?",
                "options": ["concurrency", "parallelism", "isolation", "consistency"],
                "answer": "concurrency",
                "explain": "Concurrency means handling multiple tasks at the same time.",
            }
        ]
    }
    assert validate("word_quiz", valid_choice, {"words": [{"word": "concurrency"}]}) == []

    # 3 options -> error
    too_few_opts = {
        "questions": [
            {
                "type": "choice",
                "word": "concurrency",
                "stem": "Stem",
                "options": ["A", "B", "C"],
                "answer": "A",
                "explain": "Exp",
            }
        ]
    }
    errs = validate("word_quiz", too_few_opts, {"words": [{"word": "concurrency"}]})
    assert any("4 个选项" in e for e in errs)

    # 5 options -> error
    too_many_opts = {
        "questions": [
            {
                "type": "choice",
                "word": "concurrency",
                "stem": "Stem",
                "options": ["A", "B", "C", "D", "E"],
                "answer": "A",
                "explain": "Exp",
            }
        ]
    }
    errs = validate("word_quiz", too_many_opts, {"words": [{"word": "concurrency"}]})
    assert any("4 个选项" in e for e in errs)

    # Answer not in options -> error
    ans_mismatch = {
        "questions": [
            {
                "type": "choice",
                "word": "concurrency",
                "stem": "Stem",
                "options": ["A", "B", "C", "D"],
                "answer": "Z",
                "explain": "Exp",
            }
        ]
    }
    errs = validate("word_quiz", ans_mismatch, {"words": [{"word": "concurrency"}]})
    assert any("answer 'Z' 必须在 options 中" in e for e in errs)


def test_validate_word_quiz_cloze_leak_detection():
    # Stem contains answer as standalone word (case insensitive leak)
    leaked = {
        "questions": [
            {
                "type": "cloze",
                "word": "bandwidth",
                "stem": "The Bandwidth of this link is very high.",
                "options": [],
                "answer": "bandwidth",
                "explain": "Exp",
            }
        ]
    }
    errs = validate("word_quiz", leaked, {"words": [{"word": "bandwidth"}]})
    assert any("cloze 题干不得直接包含答案原词" in e for e in errs)

    # Stem uses blank placeholder -> valid
    valid_cloze = {
        "questions": [
            {
                "type": "cloze",
                "word": "bandwidth",
                "stem": "The ___ of this network connection determines data transfer speed.",
                "options": [],
                "answer": "bandwidth",
                "explain": "Exp",
            }
        ]
    }
    assert validate("word_quiz", valid_cloze, {"words": [{"word": "bandwidth"}]}) == []


def test_validate_word_quiz_en2zh_type():
    en2zh_quiz = {
        "questions": [
            {
                "type": "en2zh",
                "word": "benchmark",
                "stem": "Translate 'benchmark' into Chinese based on context.",
                "options": [],
                "answer": "基准测试",
                "explain": "benchmark 指基准性能测试。",
            }
        ]
    }
    assert validate("word_quiz", en2zh_quiz, {"words": [{"word": "benchmark"}]}) == []


def test_validate_word_quiz_input_coverage_and_ratios():
    inp = {"words": [{"word": "apple"}, {"word": "banana"}]}

    # 1. Missing one of the input words
    missing_quiz = {
        "questions": [
            {
                "type": "cloze",
                "word": "apple",
                "stem": "Eat an ___ every day.",
                "options": [],
                "answer": "apple",
                "explain": "Exp",
            }
        ]
    }
    errs = validate("word_quiz", missing_quiz, inp)
    assert any("缺失单词: banana" in e for e in errs)

    # 2. Too many questions (> 2 * input_words = 4)
    too_many_quiz = {
        "questions": [
            {
                "type": "cloze",
                "word": "apple",
                "stem": f"Stem {i}",
                "options": [],
                "answer": "apple",
                "explain": "Exp",
            }
            for i in range(5)
        ]
    }
    errs_count = validate("word_quiz", too_many_quiz, inp)
    assert any("超过输入词数的 2 倍" in e for e in errs_count)


def test_canonical_input_word_quiz():
    raw_input = {
        "words": [
            {"word": " Zoo ", "cn": "动物园"},
            {"word": "apple", "cn": "苹果"},
            {"word": "ZOO", "cn": "动物园（大写）"},
            {"word": " Banana ", "cn": "香蕉"},
        ]
    }
    canonical = canonical_input("word_quiz", raw_input)
    parsed = json.loads(canonical)

    # Must be deduplicated (case-insensitively) and sorted by word
    assert len(parsed["words"]) == 3
    words = [w["word"] for w in parsed["words"]]
    assert words == ["apple", "Banana", "Zoo"]


def test_quiz_request_models_validation():
    # Valid item
    item = QuizWordItem(word="  microservice  ", cn="微服务")
    assert item.word == "microservice"
    assert item.cn == "微服务"

    # Invalid item: no letters
    with pytest.raises(ValidationError):
        QuizWordItem(word="12345")

    # Invalid item: empty word
    with pytest.raises(ValidationError):
        QuizWordItem(word="   ")

    # Invalid item: too long word (> 64)
    with pytest.raises(ValidationError):
        QuizWordItem(word="a" * 65)

    # Invalid item: cn too long (> 100)
    with pytest.raises(ValidationError):
        QuizWordItem(word="test", cn="词" * 101)

    # QuizRequest: empty words list
    with pytest.raises(ValidationError):
        QuizRequest(words=[])

    # QuizRequest: > 20 words
    with pytest.raises(ValidationError):
        QuizRequest(words=[QuizWordItem(word=f"word{i}") for i in range(21)])
