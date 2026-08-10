from app.utils.scoring import compute_opportunity_score


def test_not_visible_high_volume_low_difficulty_scores_high():
    score = compute_opportunity_score(
        "Frase vs Surfer SEO which is better", 1200, 62, domain_visible=False
    )
    assert 0.6 < score <= 1.0


def test_visible_low_volume_high_difficulty_scores_low():
    score = compute_opportunity_score("what is seo", 50, 90, domain_visible=True)
    assert 0.0 <= score < 0.4


def test_scores_are_ordered_correctly_by_visibility_gap():
    visible = compute_opportunity_score("best seo tool", 1000, 50, domain_visible=True)
    not_visible = compute_opportunity_score("best seo tool", 1000, 50, domain_visible=False)
    assert not_visible > visible, "an invisible domain must score higher than a visible one, all else equal"


def test_score_always_bounded_0_to_1():
    for volume in [0, 1, 100, 100_000]:
        for difficulty in [0, 50, 100]:
            for visible in [True, False, None]:
                score = compute_opportunity_score("test query", volume, difficulty, visible)
                assert 0.0 <= score <= 1.0


def test_commercial_intent_scores_higher_than_informational_all_else_equal():
    commercial = compute_opportunity_score("Frase vs Surfer SEO comparison", 500, 50, domain_visible=False)
    informational = compute_opportunity_score("what does content brief mean", 500, 50, domain_visible=False)
    assert commercial > informational
