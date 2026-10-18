import json

import pytest

from tongyun_learn.ai.prompts import (
    SENTENCE_GRAMMAR_SYSTEM_PROMPT,
    WORD_DECK_SYSTEM_PROMPT,
    WORD_MNEMONIC_SYSTEM_PROMPT,
    WORD_QUIZ_SYSTEM_PROMPT,
    build_messages,
    repair_message,
)
from tongyun_learn.ai.service import cache_key, canonical_input


def test_canonical_input_word_mnemonic():
    raw1 = {"word": "  abandon  ", "context": "  放弃  "}
    raw2 = {"context": "放弃", "word": "abandon"}
    assert canonical_input("word_mnemonic", raw1) == canonical_input("word_mnemonic", raw2)
    parsed = json.loads(canonical_input("word_mnemonic", raw1))
    assert parsed == {"context": "放弃", "word": "abandon"}


def test_canonical_input_sentence_grammar():
    raw1 = {"sentence": "The   database   optimizes\nqueries.", "context": "技术  英语"}
    raw2 = {"sentence": "The database optimizes queries.", "context": "技术 英语"}
    assert canonical_input("sentence_grammar", raw1) == canonical_input("sentence_grammar", raw2)
    parsed = json.loads(canonical_input("sentence_grammar", raw1))
    assert parsed == {"context": "技术 英语", "sentence": "The database optimizes queries."}


def test_canonical_input_word_quiz():
    raw1 = {
        "words": [
            {"word": "Ability", "cn": "能力"},
            {"word": "abandon", "cn": "放弃"},
            {"word": "ABANDON", "cn": "重复放弃"},  # 大小写去重
            "not_a_dict",  # 非 dict 过滤
        ]
    }
    canon = canonical_input("word_quiz", raw1)
    parsed = json.loads(canon)
    # 按小写排序，重复项过滤
    assert parsed["words"] == [
        {"cn": "放弃", "word": "abandon"},
        {"cn": "能力", "word": "Ability"},
    ]


def test_canonical_input_word_deck():
    raw1 = {"scenario": "  外企  技术   面试  ", "n": 10}
    raw2 = {"scenario": "外企 技术 面试", "n": "10"}
    assert canonical_input("word_deck", raw1) == canonical_input("word_deck", raw2)

    # 非法 n 回退为 20
    raw_invalid_n = {"scenario": "面试", "n": "invalid"}
    parsed = json.loads(canonical_input("word_deck", raw_invalid_n))
    assert parsed["n"] == 20
    assert parsed["scenario"] == "面试"


def test_canonical_input_fallback():
    raw = {"b": 2, "a": 1}
    assert canonical_input("custom_kind", raw) == '{"a":1,"b":2}'


def test_cache_key():
    k1 = cache_key("word_mnemonic", "gemini-3-8-flash-openai", "w1", '{"context":"","word":"abandon"}')
    k2 = cache_key("word_mnemonic", "gemini-3-8-flash-openai", "w1", '{"context":"","word":"abandon"}')
    assert k1 == k2
    assert len(k1) == 64

    # 任何一个组件不同都会改变 cache_key
    k3 = cache_key("word_mnemonic", "deepseek-v4-1-flash", "w1", '{"context":"","word":"abandon"}')
    assert k1 != k3


def test_build_messages_word_mnemonic():
    # 无 context
    msgs = build_messages("word_mnemonic", {"word": "abandon"})
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == WORD_MNEMONIC_SYSTEM_PROMPT
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "单词：abandon"

    # 有 context
    msgs_ctx = build_messages("word_mnemonic", {"word": "abandon", "context": "抛弃"})
    assert "参考释义：抛弃" in msgs_ctx[1]["content"]


def test_build_messages_sentence_grammar():
    msgs = build_messages("sentence_grammar", {"sentence": "Hello world.", "context": "口语"})
    assert len(msgs) == 2
    assert msgs[0]["content"] == SENTENCE_GRAMMAR_SYSTEM_PROMPT
    assert "句子：Hello world." in msgs[1]["content"]
    assert "上下文（仅供理解，不要讲解它）：口语" in msgs[1]["content"]


def test_build_messages_word_quiz():
    msgs = build_messages(
        "word_quiz",
        {"words": [{"word": "abandon", "cn": "放弃"}, {"word": "ability"}]},
    )
    assert len(msgs) == 2
    assert msgs[0]["content"] == WORD_QUIZ_SYSTEM_PROMPT
    assert "- abandon（参考释义：放弃）" in msgs[1]["content"]
    assert "- ability" in msgs[1]["content"]


def test_build_messages_word_deck():
    msgs = build_messages("word_deck", {"scenario": "技术面试", "n": 15})
    assert len(msgs) == 2
    assert msgs[0]["content"] == WORD_DECK_SYSTEM_PROMPT
    assert "场景：技术面试" in msgs[1]["content"]
    assert "不超过 15 个词汇" in msgs[1]["content"]


def test_build_messages_unknown_kind():
    with pytest.raises(ValueError, match="Unknown kind"):
        build_messages("unknown_kind", {})


def test_repair_message():
    errs = ["错误1", "错误2", "错误3", "错误4", "错误5", "错误6（超过5个应被截断）"]
    msg = repair_message(errs)
    assert msg["role"] == "user"
    assert "错误1；错误2；错误3；错误4；错误5" in msg["content"]
    assert "错误6" not in msg["content"]
    assert "请只输出修正后的完整 JSON 对象" in msg["content"]

    empty_msg = repair_message([])
    assert empty_msg["role"] == "user"
