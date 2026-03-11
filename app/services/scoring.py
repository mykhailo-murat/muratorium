from __future__ import annotations

CRITICAL_KEYWORDS = {
    "\u0432\u0431\u0438\u0432\u0441\u0442\u0432",
    "\u0437\u0430\u043c\u0430\u0445",
    "\u043b\u0456\u043a\u0432\u0456\u0434",
    "\u0434\u0435\u0440\u0436\u043f\u0435\u0440\u0435\u0432\u043e\u0440\u043e\u0442",
    "\u043f\u0435\u0440\u0435\u0432\u043e\u0440\u043e\u0442",
    "\u044f\u0434\u0435\u0440\u043d",
    "nuclear",
    "assassinat",
    "coup",
    "\u0431\u0456\u043e \u0437\u0430\u0433\u0440\u043e\u0437",
    "\u043d\u043e\u0432\u0438\u0439 \u0448\u0442\u0430\u043c",
    "pandemic",
    "state of emergency",
    "emergency declaration",
    "biological threat",
    "new variant",
    "deadly variant",
}

HIGH_KEYWORDS = {
    "\u043c\u0430\u0441\u043e\u0432\u0430\u043d",
    "\u043f\u0440\u0435\u0437\u0438\u0434\u0435\u043d\u0442",
    "\u043b\u0456\u0434\u0435\u0440",
    "\u0432\u0456\u0439\u043d",
    "\u0432\u0442\u043e\u0440\u0433\u043d\u0435\u043d",
    "\u0430\u0442\u0430\u043a",
    "\u043d\u0430\u0446\u0431\u0435\u0437\u043f\u0435\u043a",
    "\u0441\u0443\u0434",
    "\u0443\u0440\u0430\u0436\u0435\u043d",
    "\u0454\u0441",
    "\u0441\u0448\u0430",
    "\u0440\u043e\u0437\u0441\u043b\u0456\u0434\u0443\u0432\u0430\u043d",
    "\u0443\u043a\u0440\u0430\u0457\u043d",
    "\u0440\u0430\u043a\u0435\u0442",
    "\u043e\u0431\u0441\u0442\u0440\u0456\u043b",
    "\u0443\u0434\u0430\u0440",
    "\u0432\u0442\u043e\u0440\u0433\u043d\u0435\u043d",
    "\u0442\u0435\u0440\u0430\u043a\u0442",
    "martial law",
    "mobilization",
    "\u0435\u0432\u0430\u043a\u0443\u0430\u0446",
    "attack",
    "missile",
    "explosion",
    "airstrike",
    "drone strike",
    "major escalation",
    "siege",
}

MEDIUM_KEYWORDS = {
    "\u0441\u0430\u043d\u043a\u0446",
    "\u0443\u043b\u044c\u0442\u0438\u043c\u0430\u0442\u0443\u043c",
    "\u043d\u0430\u0444\u0442",
    "oil reserve",
    "strategic reserve",
    "\u043f\u0435\u0440\u0435\u0433\u043e\u0432\u043e\u0440",
    "aid package",
    "nato",
    "iran",
    "israel",
    "\u0432\u0456\u0439\u043d",
    "war",
    "\u0432\u043e\u0454\u043d",
    "ceasefire",
    "troop",
    "military aid",
}

LOW_SIGNAL_KEYWORDS = {
    "\u0437\u0430\u044f\u0432\u0438",
    "\u0440\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0443",
    "\u043e\u0447\u0456\u043a\u0443",
    "\u043f\u0440\u043e\u0433\u043d\u043e\u0437",
    "\u043a\u043e\u043c\u0435\u043d\u0442\u0430\u0440",
    "advisory",
    "recommend",
    "forecast",
    "statement",
    "urges",
    "calls for",
    "says",
    "according to",
}


def _count_hits(text: str, keywords: set[str]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def _score_cap(critical_hits: int, high_hits: int, medium_hits: int) -> int:
    if critical_hits > 0:
        return 100
    if high_hits > 0:
        return 88
    if medium_hits > 0:
        return 78
    return 60


def calc_score(
    trust_score_1_10: int,
    title: str,
    content: str,
    source_count: int = 1,
) -> int:
    # trust_score is kept for backward compatibility but intentionally weak in final pre-score.
    _ = trust_score_1_10
    text = (title + " " + content).lower()

    critical_hits = _count_hits(text, CRITICAL_KEYWORDS)
    high_hits = _count_hits(text, HIGH_KEYWORDS)
    medium_hits = _count_hits(text, MEDIUM_KEYWORDS)
    low_signal_hits = _count_hits(text, LOW_SIGNAL_KEYWORDS)

    score = 20
    score += min(critical_hits * 60, 80)
    score += min(high_hits * 12, 30)
    score += min(medium_hits * 7, 21)
    score += min(max(source_count - 1, 0) * 3, 12)

    score -= min(low_signal_hits * 8, 24)

    cap = _score_cap(critical_hits, high_hits, medium_hits)
    return max(0, min(score, cap))


def is_breaking(score: int) -> bool:
    return score >= 96
