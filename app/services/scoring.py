KEYWORDS_HIGH = {
    "удар", "ракета", "ракет", "обстріл", "ескалац", "вторгнен",
    "санкц", "пакет допомоги", "nato", "iran", "israel", "strike", "missile",
}


def calc_score(trust_score_1_10: int, title: str, content: str) -> int:
    # Simple MVP scoring: trust + keyword boost
    score = trust_score_1_10 * 8  # 8..80
    text = (title + " " + content).lower()

    hit = any(k in text for k in KEYWORDS_HIGH)
    if hit:
        score += 20

    return min(score, 100)


def is_breaking(score: int) -> bool:
    return score >= 90
