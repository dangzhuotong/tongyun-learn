import hashlib
import re
import unicodedata

_WS = re.compile(r"\s+")


def normalize_front(front: str) -> str:
    """规范化 front：NFKC、合并空白、去首尾空白、大小写不敏感。en_word 卡即小写单词。"""
    s = unicodedata.normalize("NFKC", front or "")
    return _WS.sub(" ", s).strip().casefold()


def front_key(front: str) -> str:
    return hashlib.sha256(normalize_front(front).encode("utf-8")).hexdigest()
