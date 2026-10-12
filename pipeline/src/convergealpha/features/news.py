"""News sentiment (Loughran-McDonald word lists) and keyword event tags for headlines.

The LM lists are free for non-commercial research; they live only in the private data repo
(reference/lm_sentiment_words.csv). Without them a small built-in finance lexicon is used and
the output says so. The AI event layer (spec F7) only runs when ANTHROPIC_API_KEY is set.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

_WORD = re.compile(r"[A-Za-z]+")

_FALLBACK_NEG = {
    "loss", "losses", "decline", "declines", "declined", "fall", "falls", "fell", "drop", "drops", "dropped",
    "weak", "weaker", "miss", "missed", "misses", "lawsuit", "fraud", "investigation", "probe", "downgrade",
    "downgraded", "cut", "cuts", "lowered", "warning", "warns", "bankruptcy", "default", "delay", "delayed",
    "recall", "layoffs", "plunge", "plunges", "slump", "slumps", "concern", "concerns", "risk", "risks",
}  # fmt: skip
_FALLBACK_POS = {
    "gain", "gains", "growth", "grows", "rise", "rises", "rose", "beat", "beats", "strong", "stronger",
    "record", "upgrade", "upgraded", "raises", "raised", "approval", "approved", "surge", "surges",
    "profit", "profitable", "improve", "improved", "improves", "outperform", "win", "wins", "expands",
}  # fmt: skip


@dataclass
class Lexicon:
    negative: set[str]
    positive: set[str]
    uncertainty: set[str]
    litigious: set[str]
    name: str


def load_lexicon(data_dir: Path) -> Lexicon:
    p = data_dir / "reference" / "lm_sentiment_words.csv"
    if p.is_file():
        df = pd.read_csv(p)
        w = df["Word"].astype(str).str.lower()
        return Lexicon(
            negative=set(w[df["Negative"] > 0]),
            positive=set(w[df["Positive"] > 0]),
            uncertainty=set(w[df["Uncertainty"] > 0]),
            litigious=set(w[df["Litigious"] > 0]),
            name="Loughran-McDonald",
        )
    return Lexicon(_FALLBACK_NEG, _FALLBACK_POS, set(), set(), "built-in fallback")


def sentiment(text: str, lex: Lexicon) -> tuple[float, int, int]:
    """(score in [-1, 1], positive count, negative count). Score = (pos-neg)/(pos+neg+1)."""
    words = [w.lower() for w in _WORD.findall(text or "")]
    pos = sum(w in lex.positive for w in words)
    neg = sum(w in lex.negative for w in words)
    return (pos - neg) / (pos + neg + 1), pos, neg


# (tag, pattern, direction) — direction -2..+2 is a rough prior, not a trading signal.
TAGS: list[tuple[str, re.Pattern[str], int]] = [
    (
        "offering",
        re.compile(
            r"\b(public|secondary|follow-on|registered direct|stock|share|equity) offering\b|\bat-the-market\b|\bprices? .{0,40}offering\b",
            re.I,
        ),
        -1,
    ),
    (
        "merger_target",
        re.compile(
            r"\b(to be acquired|agrees? to be acquired|agreed to be bought|takeover (bid|offer|approach)|buyout (offer|bid)|goes private|take[- ]private)\b",
            re.I,
        ),
        1,
    ),
    (
        "investigation",
        re.compile(
            r"\b(SEC|DOJ|Department of Justice|FTC) (probe|investigation|inquiry|charges|subpoena)|\bsubpoena|\bunder investigation\b|\bfederal probe\b",
            re.I,
        ),
        -2,
    ),
    (
        "fda",
        re.compile(
            r"\b(FDA|PDUFA|advisory committee|complete response letter|CRL|BLA|NDA)\b", re.I
        ),
        0,
    ),
    ("going_concern", re.compile(r"going[- ]concern", re.I), -2),
    ("auditor", re.compile(r"auditor (resign|resigns|resigned|resignation|dismiss)", re.I), -2),
    (
        "restatement",
        re.compile(r"\b(restate|restates|restated|restatement|non-reliance)\b", re.I),
        -2,
    ),
    (
        "guidance_up",
        re.compile(
            r"\b(raises|raised|lifts|lifted|boosts|boosted|ups|hikes) (its |full-year |annual |fy\d* )?(guidance|outlook|forecast)",
            re.I,
        ),
        1,
    ),
    (
        "guidance_down",
        re.compile(
            r"\b(cuts|cut|lowers|lowered|slashes|slashed|withdraws|trims|reduces) (its |full-year |annual |fy\d* )?(guidance|outlook|forecast)",
            re.I,
        ),
        -1,
    ),
    (
        "buyback",
        re.compile(r"\b(buyback|share repurchase|stock repurchase|repurchase program)\b", re.I),
        1,
    ),
    (
        "dividend_up",
        re.compile(r"\b(raises|increases|hikes|boosts) (its |quarterly )?dividend", re.I),
        1,
    ),
    (
        "dividend_down",
        re.compile(r"\b(cuts|suspends|slashes|eliminates) (its |quarterly )?dividend", re.I),
        -1,
    ),
    ("lawsuit", re.compile(r"\bclass action\b|\blawsuit\b|\bsued\b", re.I), -1),
    ("upgrade", re.compile(r"\bupgrade[sd]?\b", re.I), 1),
    ("downgrade", re.compile(r"\bdowngrade[sd]?\b", re.I), -1),
]


def tag(text: str) -> list[tuple[str, int]]:
    return [(name, d) for name, pat, d in TAGS if pat.search(text or "")]


def score_news(news: pd.DataFrame, lex: Lexicon) -> pd.DataFrame:
    if news.empty:
        return news.assign(sentiment=pd.Series(dtype=float), tags=pd.Series(dtype=object))
    texts = (news["headline"].fillna("") + ". " + news["summary"].fillna("")).tolist()
    scored = [sentiment(t, lex) for t in texts]
    tags = [tag(h) for h in news["headline"].fillna("").tolist()]
    return news.assign(
        sentiment=[s[0] for s in scored],
        tags=[",".join(n for n, _ in t) for t in tags],
        tag_direction=[
            min((d for _, d in t), default=0)
            if any(d < 0 for _, d in t)
            else max((d for _, d in t), default=0)
            for t in tags
        ],
    )


def per_ticker(news: pd.DataFrame, as_of: pd.Timestamp, days: int = 10) -> pd.DataFrame:
    """Average sentiment and negative-tag flags over the last `days` days."""
    if news.empty:
        return pd.DataFrame(columns=["news_sentiment", "news_count", "news_negative_tags"])
    w = news[(news["datetime"] <= as_of) & (news["datetime"] > as_of - pd.Timedelta(days=days))]
    g = w.groupby("ticker")
    out = pd.DataFrame({"news_sentiment": g["sentiment"].mean(), "news_count": g.size()})
    neg = w[w["tag_direction"] < 0]
    out["news_negative_tags"] = neg.groupby("ticker")["tags"].agg(
        lambda s: ",".join(sorted({t for x in s for t in str(x).split(",") if t}))
    )
    return out


def tags_in(news: pd.DataFrame, names: Iterable[str]) -> pd.DataFrame:
    want = set(names)
    if news.empty:
        return news
    mask = news["tags"].fillna("").apply(lambda s: bool(want & set(s.split(","))))
    return news[mask]
