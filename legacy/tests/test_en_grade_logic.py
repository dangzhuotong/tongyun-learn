from tongyun_learn.services.en_grade import classify_mismatch, grade_attempt, normalize, rating_for


def test_normalize_nfkc_fullwidth_and_whitespace():
    assert normalize("  Ｃａｆé  ", ignore_case=True, loose_punct=False) == "café"
    assert normalize("Hello   World", ignore_case=False, loose_punct=False) == "Hello World"


def test_normalize_curly_quotes_fold_to_ascii():
    assert normalize("don’t  stop", ignore_case=True, loose_punct=True) == "don't stop"
    assert normalize("“read”", ignore_case=True, loose_punct=False) == '"read"'


def test_normalize_loose_punct_keeps_inner_hyphen_and_apostrophe():
    assert normalize("well-known, ok!", ignore_case=True, loose_punct=True) == "well-known ok"
    assert normalize("well-known, ok!", ignore_case=True, loose_punct=False) == "well-known, ok!"


def test_normalize_empty_and_none():
    assert normalize(None, ignore_case=True, loose_punct=True) == ""
    assert normalize("", ignore_case=True, loose_punct=True) == ""


def test_classify_substitution_and_transposition():
    assert classify_mismatch("read", "reed") == "substitution"
    assert classify_mismatch("read", "raed") == "transposition"


def test_classify_empty_typed():
    assert classify_mismatch("read", "") == "empty"


def test_classify_prefix_and_extra_letter():
    assert classify_mismatch("read", "bread") == "prefix"
    assert classify_mismatch("hello", "helllo") == "extra_letter"


def test_classify_missing_letter_and_suffix():
    assert classify_mismatch("hello", "hllo") == "missing_letter"
    assert classify_mismatch("read", "ready") == "suffix"


def test_classify_near_word_and_other():
    assert classify_mismatch("abcdef", "abxyef") == "near_word"
    assert classify_mismatch("abc", "xyz") == "other"


def test_classify_case_and_punctuation():
    assert classify_mismatch("read", "Read") == "case"
    assert classify_mismatch("read", "read.") == "punctuation"


def test_grade_sentence_phase_ignores_punctuation_but_word_phase_does_not():
    assert grade_attempt("Hello, world!", "hello world", "B") == (True, None)
    assert grade_attempt("Hello, world!", "hello world", "A") == (False, "punctuation")


def test_grade_phase_between_word_phase_is_case_insensitive_by_default():
    assert grade_attempt("read", "READ", "A") == (True, None)
    assert grade_attempt("read", "READ", "A", ignore_case=False) == (False, "case")


def test_rating_for_attempt_buckets():
    assert rating_for(True, 0) == 3
    assert rating_for(True, 1) == 3
    assert rating_for(True, 3) == 2
    assert rating_for(False, 0) == 1
    assert rating_for(False, 5) == 1
