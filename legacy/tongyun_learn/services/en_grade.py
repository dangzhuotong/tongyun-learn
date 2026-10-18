"""手敲判分。词阶段认大小写配置、保留标点；句阶段标点宽松。"""

from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")
# 去掉标点，但留下单词内部的连字符和撇号（thread-safe、don't）。
_PUNCT = re.compile(r"[^\w\s'-]+", re.UNICODE)

ERROR_SHAPES = (
    "case",
    "punctuation",
    "missing_letter",
    "extra_letter",
    "prefix",
    "suffix",
    "transposition",
    "substitution",
    "near_word",
    "empty",
    "other",
)


def normalize(text: str, *, ignore_case: bool, loose_punct: bool) -> str:
    s = unicodedata.normalize("NFKC", text or "")
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    if loose_punct:
        s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    if ignore_case:
        s = s.casefold()
    return s


def _compact(text: str) -> str:
    return normalize(text, ignore_case=True, loose_punct=True).replace(" ", "")


def _levenshtein(a: str, b: str, limit: int = 4) -> int:
    if a == b:
        return 0
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        row_min = i
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (ca != cb)
            val = min(ins, delete, sub)
            cur.append(val)
            if val < row_min:
                row_min = val
        if row_min > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def classify_mismatch(expected: str, typed: str) -> str:
    """在已经判定不相等之后，给一个错误形态标签。"""
    same_case = normalize(expected, ignore_case=True, loose_punct=False) == normalize(
        typed, ignore_case=True, loose_punct=False
    )
    if same_case:
        return "case"
    same_punct = normalize(expected, ignore_case=True, loose_punct=True) == normalize(
        typed, ignore_case=True, loose_punct=True
    )
    if same_punct:
        return "punctuation"
    e = _compact(expected)
    t = _compact(typed)
    if not t:
        return "empty"
    if len(e) == len(t) and e != t:
        diffs = [i for i, (a, b) in enumerate(zip(e, t, strict=True)) if a != b]
        swapped = (
            len(diffs) == 2
            and diffs[1] == diffs[0] + 1
            and e[diffs[0]] == t[diffs[1]]
            and e[diffs[1]] == t[diffs[0]]
        )
        if swapped:
            return "transposition"
        if len(diffs) == 1:
            return "substitution"
    # 一方是另一方的前缀：结尾多了或少了，记成前后缀问题。
    if e.startswith(t) or t.startswith(e):
        if min(len(e), len(t)) >= 3 and abs(len(e) - len(t)) <= 4:
            return "suffix"
        return "missing_letter" if len(t) < len(e) else "extra_letter"
    if len(t) < len(e) and e.endswith(t) and len(t) >= 2:
        return "prefix"
    if len(t) > len(e) and t.endswith(e) and len(e) >= 2:
        return "prefix"
    dist = _levenshtein(e, t)
    if dist == 1 and len(t) == len(e) - 1:
        return "missing_letter"
    if dist == 1 and len(t) == len(e) + 1:
        return "extra_letter"
    if dist == 1:
        return "substitution"
    shared = 0
    for a, b in zip(e, t, strict=False):
        if a != b:
            break
        shared += 1
    if shared >= max(2, len(e) // 2) and abs(len(e) - len(t)) <= 3:
        return "suffix"
    if dist <= 2:
        return "near_word"
    return "other"


def grade_attempt(expected: str, typed: str, phase: str, *, ignore_case: bool = True) -> tuple[bool, str | None]:
    """返回 (是否正确, 错误形态)。正确时错误形态为 None。句阶段（B）忽略标点。"""
    loose = phase == "B"
    if normalize(expected, ignore_case=ignore_case, loose_punct=loose) == normalize(
        typed, ignore_case=ignore_case, loose_punct=loose
    ):
        return True, None
    if not ignore_case and normalize(expected, ignore_case=True, loose_punct=loose) == normalize(
        typed, ignore_case=True, loose_punct=loose
    ):
        return False, "case"
    return False, classify_mismatch(expected, typed)


def rating_for(correct: bool, attempts: int) -> int:
    """第一次敲对记 Good；用了一次修正才对记 Hard；敲错记 Again。"""
    if not correct:
        return 1
    if attempts <= 1:
        return 3
    return 2
