"""
Text cleaning utilities for ingested trend items.

Responsibilities
----------------
- Remove URLs and bare domain strings
- Optionally strip emoji characters
- Normalise Unicode (NFKC)
- Collapse whitespace
- Remove excess punctuation

All public functions are pure and stateless so they can be composed freely.
"""

from __future__ import annotations

import re
import unicodedata

# ── Compiled patterns (pre-compiled for performance) ──────────────────────────

_URL_RE = re.compile(
    r"https?://\S+|www\.\S+",
    re.IGNORECASE,
)
_SUBREDDIT_RE = re.compile(r"r/\w+", re.IGNORECASE)
_EXCESS_PUNCT_RE = re.compile(r"[^\w\s\-.,!?'\"()]+")
_MULTI_SPACE_RE = re.compile(r"\s{2,}")
_LEADING_TRAILING_PUNCT_RE = re.compile(r"^[\s\W]+|[\s\W]+$")

# Unicode "Other" categories that include emoji/pictographs
_EMOJI_CATEGORIES = {"So", "Sm", "Sk", "Sc"}


# ── Individual cleaning steps ─────────────────────────────────────────────────

def remove_urls(text: str) -> str:
    """Remove http(s) URLs and bare ``www.*`` links from *text*."""
    return _URL_RE.sub(" ", text)


def remove_subreddit_mentions(text: str) -> str:
    """Remove subreddit references like ``r/AskReddit``."""
    return _SUBREDDIT_RE.sub(" ", text)


def remove_emojis(text: str) -> str:
    """
    Strip emoji and other non-alphanumeric Unicode symbols.

    Uses Unicode category checks, which is more accurate than a regex
    character class and handles all future emoji additions automatically.
    """
    return "".join(
        ch for ch in text if unicodedata.category(ch) not in _EMOJI_CATEGORIES
    )


def normalize_unicode(text: str) -> str:
    """Apply NFKC normalisation to fold compatibility characters."""
    return unicodedata.normalize("NFKC", text)


def normalize_case(text: str) -> str:
    """Convert text to lower-case for uniform comparisons."""
    return text.lower()


def strip_excess_punctuation(text: str) -> str:
    """Remove characters that are neither word characters nor common punctuation."""
    return _EXCESS_PUNCT_RE.sub(" ", text)


def collapse_whitespace(text: str) -> str:
    """Replace any run of whitespace with a single space and strip edges."""
    return _MULTI_SPACE_RE.sub(" ", text).strip()


# ── Composed cleaning pipeline ────────────────────────────────────────────────

def clean_text(
    text: str,
    *,
    strip_urls: bool = True,
    strip_emojis: bool = True,
    lowercase: bool = True,
    strip_reddit_mentions: bool = True,
) -> str:
    """
    Apply the full cleaning pipeline to a single text string.

    Steps (in order):
      1. Unicode normalisation (NFKC)
      2. Remove URLs                     (if ``strip_urls=True``)
      3. Remove subreddit mentions        (if ``strip_reddit_mentions=True``)
      4. Remove emojis                    (if ``strip_emojis=True``)
      5. Strip excess punctuation
      6. Lower-case                       (if ``lowercase=True``)
      7. Collapse whitespace

    Args:
        text:                    Input string.
        strip_urls:              Remove http/www URLs.
        strip_emojis:            Remove emoji characters.
        lowercase:               Convert to lower-case.
        strip_reddit_mentions:   Remove ``r/subreddit`` patterns.

    Returns:
        Cleaned string.
    """
    text = normalize_unicode(text)

    if strip_urls:
        text = remove_urls(text)

    if strip_reddit_mentions:
        text = remove_subreddit_mentions(text)

    if strip_emojis:
        text = remove_emojis(text)

    text = strip_excess_punctuation(text)

    if lowercase:
        text = normalize_case(text)

    text = collapse_whitespace(text)
    return text


def clean_item_title(title: str, source: str = "") -> str:
    """
    Clean a trend item title with source-appropriate settings.

    Args:
        title:  Raw title string.
        source: Source name (e.g. ``"reddit"``).  Used for source-specific rules.

    Returns:
        Cleaned title string.
    """
    strip_reddit = source.lower() == "reddit"
    return clean_text(
        title,
        strip_urls=True,
        strip_emojis=True,
        lowercase=True,
        strip_reddit_mentions=strip_reddit,
    )
