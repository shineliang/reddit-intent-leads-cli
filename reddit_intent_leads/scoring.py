from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class IntentResult:
    score: float
    signals: list[str]


_INTENT_RULES: list[tuple[str, re.Pattern[str], float]] = [
    ("looking_for", re.compile(r"\b(looking for|need|seeking|want)\b", re.I), 2.0),
    ("recommend", re.compile(r"\b(recommend|recommendation|any suggestions|suggest)\b", re.I), 1.5),
    ("alternative", re.compile(r"\b(alternative|replacement|instead of)\b", re.I), 2.0),
    ("pricing", re.compile(r"\b(price|pricing|expensive|too expensive|budget)\b", re.I), 1.0),
    ("demo_trial", re.compile(r"\b(trial|demo|free trial)\b", re.I), 0.8),
    ("b2b_words", re.compile(r"\b(crm|pipeline|lead|prospect|invoic|quote|proposal|client)\b", re.I), 0.8),
]

_NEGATIVE_RULES: list[tuple[str, re.Pattern[str], float]] = [
    ("rant", re.compile(r"\b(rant|vent)\b", re.I), -0.8),
    ("no_buy", re.compile(r"\b(not buying|won't buy|never pay)\b", re.I), -1.5),
]


def score_intent(text: str) -> IntentResult:
    s = 0.0
    signals: list[str] = []

    for name, rx, w in _INTENT_RULES:
        if rx.search(text or ""):
            s += w
            signals.append(name)

    for name, rx, w in _NEGATIVE_RULES:
        if rx.search(text or ""):
            s += w
            signals.append(name)

    # normalize-ish
    if s < 0:
        s = 0.0

    return IntentResult(score=s, signals=signals)
