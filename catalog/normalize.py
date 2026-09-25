"""曲名の正規化と照合。

- clean(): 保存する前の整形（NFC 化と前後の空白の除去）。見た目は変えない
- match_key(): 表記ゆれを吸収した比較用のキー。候補を探すときだけ使い、保存はしない
  （NFKC、小文字化、空白と記号 ♡♥☆★・!?~〜～…. などを除去）
"""
import re
import unicodedata

# 表記ゆれとして無視する記号（NFKC 後の文字で指定する）
_IGNORED = re.compile(r"[\s♡♥❤☆★・!?~〜∼～…\.,、。\-‐―＊*♪∞'\"“”‘’()\[\]「」『』]")


def clean(title):
    return unicodedata.normalize("NFC", title or "").strip()


def match_key(title):
    # NFKC で … は ...、～ は ~ になる。長音の「ー」は曲名の一部なので除かない
    s = unicodedata.normalize("NFKC", title or "").lower()
    return _IGNORED.sub("", s)


def resolve(title, songs_by_title, aliases, songs_by_key):
    """曲名から曲を探す。

    songs_by_title: {曲名: 曲}、aliases: {別表記: 曲}、songs_by_key: {match_key: [曲, ...]}
    戻り値: (見つかった曲 or None, 候補の曲のリスト)
    完全一致か別表記の一致なら曲を返す。見つからなければ、キーが一致する曲を候補として返す。
    """
    t = clean(title)
    if t in songs_by_title:
        return songs_by_title[t], []
    if t in aliases:
        return aliases[t], []
    return None, list(songs_by_key.get(match_key(t), []))
