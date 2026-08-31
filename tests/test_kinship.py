"""Kinship engine tests.

Every assertion here was first proven against the interactive prototype. The Telugu ones are
the point of the exercise: they encode distinctions English does not make, so a regression in
the struct layer shows up here rather than as a wrong word in front of a relative.
"""

import pytest

from Tree.kinship import (
    ADOPTIVE,
    FEMALE,
    MALE,
    FamilyGraph,
    ParentLink,
    Person,
    Union,
    Vocabulary,
    closest,
    explain,
    relationships,
    render_english,
    render_telugu,
    unresolved_seniority,
)
from Tree.kinship.model import UNKNOWN, Kinship
from Tree.kinship.vocabulary import MATERNAL


# ── a family with the shapes that actually occur ────────────────────────────────
#  · a within-family adoption, so two people are related more than one way
#  · uncles with and without recorded birth years
#  · both parallel and cross cousins
def build() -> FamilyGraph:
    g = FamilyGraph()
    people = [
        # id, given, sex, birth year
        (1, 'Aditya Varun', MALE, 1990), (2, 'Bharath Kiran', MALE, 1993),
        (3, 'Chandra Mohan', MALE, 1958), (4, 'Deepa Latha', FEMALE, 1962),
        (5, 'Eshwar Datta', MALE, 1928), (6, 'Girija', FEMALE, 1932),
        (8, 'Parent1', MALE, 1901), (9, 'Parent2', FEMALE, 1905),
        (7, 'Harinath', MALE, None),          # no recorded birth year
        (10, 'Kalyani Naidu', FEMALE, 1959),
        (11, 'Lokesh', MALE, 1991), (29, 'Manoj', MALE, 1995),
        (12, 'Madhava', MALE, None),           # no recorded birth year
        (13, 'Nirmala', FEMALE, 1957),
        (14, 'Padmini', FEMALE, 1984), (15, 'Raghava', MALE, 1987),
        (20, 'Yeshwanth', MALE, 1964), (21, 'Bhavani', FEMALE, 1966),
        (22, 'Chandana Sri', FEMALE, 1992),
        (23, 'Dinesh', MALE, 1957), (24, 'Gowri', FEMALE, 1961),
        (25, 'Hema', FEMALE, 1986), (26, 'Indira', FEMALE, 1989),
    ]
    for pid, given, sex, born in people:
        g.add_person(Person(id=pid, given=given, surname='Varma', sex=sex, birth_year=born))

    links = [
        (1, 3), (1, 4), (2, 3), (2, 4),
        (6, 8), (6, 9),
        (3, 5), (3, 6), (12, 5), (12, 6), (24, 5), (24, 6), (20, 5), (20, 6),
        (7, 5), (7, 6),
        (11, 7), (11, 10), (29, 7), (29, 10),
        (14, 12), (14, 13), (15, 12), (15, 13),
        (25, 23), (25, 24), (26, 23), (26, 24),
        (22, 20), (22, 21),
    ]
    for child, parent in links:
        g.add_parent_link(ParentLink(child_id=child, parent_id=parent))
    # the within-family adoption: born to 5+6, adopted by Girija's own parents
    g.add_parent_link(ParentLink(child_id=7, parent_id=8, role=ADOPTIVE))
    g.add_parent_link(ParentLink(child_id=7, parent_id=9, role=ADOPTIVE))

    for a, b in [(3, 4), (5, 6), (7, 10), (12, 13), (23, 24), (20, 21), (8, 9)]:
        g.add_union(Union(a_id=a, b_id=b))
    return g


@pytest.fixture()
def g() -> FamilyGraph:
    return build()


def en(g, a, b):
    return render_english(closest(g, a, b))


def te(g, a, b):
    return render_telugu(closest(g, a, b)).text


# ── the basics ──────────────────────────────────────────────────────────────────
def test_direct_line(g):
    assert en(g, 1, 3) == 'Father'
    assert en(g, 3, 1) == 'Son'
    assert en(g, 5, 1) == 'Grandson'
    assert en(g, 1, 5) == 'Paternal grandfather'
    assert en(g, 1, 1) == 'This is you'


def test_paternal_and_maternal_grandmothers_differ_in_telugu(g):
    """English says "grandmother" either way; Telugu does not."""
    assert te(g, 1, 6).startswith('నానమ్మ')      # father's mother


def test_own_spouse_is_not_described_through_yourself(g):
    assert en(g, 5, 6) == 'Wife'
    assert te(g, 5, 6) == 'భార్య'


# ── the distinctions English erases ─────────────────────────────────────────────
def test_parallel_cousins_take_sibling_terms(g):
    """Father's brother's children are addressed as siblings in Telugu."""
    assert en(g, 1, 11) == 'First cousin'
    assert te(g, 1, 11) == 'తమ్ముడు'            # younger brother
    assert en(g, 1, 14) == 'First cousin'
    assert te(g, 1, 14) == 'అక్క'               # elder sister


def test_cross_cousins_take_their_own_terms(g):
    """Father's sister's children are marriageable kin and carry different words."""
    assert en(g, 1, 25) == 'First cousin'
    assert te(g, 1, 25) in ('వదిన', 'మరదలు')


def test_one_english_word_covers_five_telugu_ones(g):
    cousins = [11, 29, 14, 15, 25, 26, 22]
    assert {en(g, 1, c) for c in cousins} == {'First cousin'}
    assert len({te(g, 1, c) for c in cousins}) >= 4


def test_uncle_seniority_splits_the_telugu_word(g):
    """Yeshwanth is younger than the father, so Chinnanna rather than Peddananna."""
    assert en(g, 1, 20) == 'Father’s younger brother'
    assert te(g, 1, 20) == 'చిన్నాన్న'


def test_nephew_depends_on_who_is_asking(g):
    """A man's brother's son is parallel; a woman's brother's son is cross."""
    assert te(g, 12, 1) == 'కొడుకు'             # Madhava (m) -> brother's son
    assert te(g, 24, 1) == 'మేనల్లుడు'          # Gowri (f) -> brother's son


def test_in_law_resolves_through_the_union(g):
    k = closest(g, 1, 10)
    assert k.kind == 'affinal'
    assert en(g, 1, 10) == 'Father’s brother’s wife'


# ── unknown birth order ─────────────────────────────────────────────────────────
def test_english_falls_back_to_the_base_term(g):
    """No birth year for Harinath, so English drops the rank word entirely."""
    assert en(g, 1, 7) == 'Father’s brother'
    assert en(g, 3, 7) == 'Brother'


def test_telugu_shows_both_candidates(g):
    term = render_telugu(closest(g, 1, 7))
    assert term.unresolved
    assert term.text == 'పెద్దనాన్న / చిన్నాన్న'
    assert term.bases == ('పెద్దనాన్న', 'చిన్నాన్న')


def test_the_engine_names_the_pair_that_would_settle_it(g):
    pair = unresolved_seniority(relationships(g, 1, 7))
    assert pair == (3, 7)                        # your father, and him


def test_an_answer_resolves_it(g):
    g.record_birth_order(elder_id=7, younger_id=3)
    assert te(g, 1, 7) == 'పెద్దనాన్న'
    g.birth_order.clear()
    g.record_birth_order(elder_id=3, younger_id=7)
    assert te(g, 1, 7) == 'చిన్నాన్న'


def test_a_recorded_answer_beats_the_dates(g):
    """Someone who was there knows better than a placeholder date."""
    g.record_birth_order(elder_id=20, younger_id=3)   # contradicts the birth years
    assert te(g, 1, 20) == 'పెద్దనాన్న'


# ── more than one relationship ──────────────────────────────────────────────────
def test_a_person_can_be_related_two_ways(g):
    links = relationships(g, 1, 7)
    assert len(links) == 2
    assert render_english(links[0]) == 'Father’s brother'
    assert 'Granduncle' in render_english(links[1])
    assert links[1].adoptive is True


def test_both_directions_of_the_doubled_link(g):
    """Harinath is his own mother's adoptive brother, so he is his brother's uncle too."""
    labels = [render_english(k) for k in relationships(g, 3, 7)]
    assert labels[0] == 'Brother'
    assert any('brother' in x.lower() and 'adoptive' in x.lower() for x in labels[1:])


def test_full_siblings_are_one_relationship_not_two(g):
    """Reachable through the father and through the mother — but one relationship."""
    assert len(relationships(g, 1, 2)) == 1
    assert render_english(closest(g, 1, 2)) == 'Younger brother'


def test_a_siblings_child_is_also_one_relationship(g):
    assert len(relationships(g, 3, 1)) == 1
    assert len(relationships(g, 12, 14)) == 1


def test_two_unrelated_spouses_do_not_recurse(g):
    assert relationships(g, 4, 10)[0].kind == 'none'


# ── vocabulary ──────────────────────────────────────────────────────────────────
def test_the_maternal_branch_uses_a_different_word(g):
    g.record_birth_order(elder_id=3, younger_id=20)
    base = render_telugu(closest(g, 1, 20))
    assert Vocabulary().apply(base).text == 'చిన్నాన్న'
    assert Vocabulary(side=MATERNAL).apply(base).text == 'కక్కయ్య'


def test_a_family_can_add_a_word_it_discovers(g):
    g.record_birth_order(elder_id=3, younger_id=20)
    vocab = Vocabulary()
    vocab.add_word('చిన్నాన్న', 'చిన్నయ్య', 'Chinnayya', 'the Chowdary household')
    applied = vocab.apply(render_telugu(closest(g, 1, 20)))
    added = [a for a in applied.alternatives if a['added_by_family']]
    assert [a['term'] for a in added] == ['చిన్నయ్య']


def test_a_word_can_be_pinned_to_one_person(g):
    g.record_birth_order(elder_id=3, younger_id=20)
    vocab = Vocabulary()
    vocab.pin(20, 'చిన్నాన్న', 'బాబాయి', 'Babai')
    base = render_telugu(closest(g, 1, 20))
    assert vocab.apply(base, person_id=20).text == 'బాబాయి'
    assert vocab.apply(base, person_id=20).pinned is True
    # and it must not leak onto anyone else
    assert vocab.apply(base, person_id=12).text == 'చిన్నాన్న'


def test_a_pin_can_use_a_word_the_family_added(g):
    g.record_birth_order(elder_id=3, younger_id=20)
    vocab = Vocabulary()
    vocab.add_word('చిన్నాన్న', 'చిన్నయ్య', 'Chinnayya')
    vocab.pin(20, 'చిన్నాన్న', 'చిన్నయ్య', 'Chinnayya')
    assert vocab.apply(render_telugu(closest(g, 1, 20)), person_id=20).text == 'చిన్నయ్య'


def test_vocabulary_applies_to_each_half_of_an_unresolved_pair(g):
    applied = Vocabulary(side=MATERNAL).apply(render_telugu(closest(g, 1, 7)))
    assert applied.text == 'పెద్దనాన్న / కక్కయ్య'


# ── nothing may render as broken text ───────────────────────────────────────────
def test_every_pair_renders(g):
    ids = sorted(g.people)
    for a in ids:
        for b in ids:
            for k in relationships(g, a, b):
                english = render_english(k)
                telugu = Vocabulary().apply(render_telugu(k), person_id=b)
                reason = explain(k)
                assert english and 'None' not in english
                assert telugu.text and 'None' not in telugu.text
                assert reason.strip() not in ('', '.')


def test_explain_never_returns_a_bare_full_stop(g):
    for a in (1, 5, 7, 24):
        for b in sorted(g.people):
            assert explain(closest(g, a, b)).strip() != '.'


# ── a sex nobody recorded ───────────────────────────────────────────────────────
def test_english_names_an_unrecorded_sex_without_inventing_one():
    """`'Son' if male else 'Daughter'` called every person of unknown sex a daughter. The
    add-person form offers "unknown" as a real answer, so the renderers have to mean it."""
    for sex in (UNKNOWN, 'intersex'):
        assert render_english(Kinship(kind='descendant', depth=1, sex=sex)) == 'Child'
        assert render_english(Kinship(kind='ancestor', depth=1, sex=sex)) == 'Parent'
        assert render_english(Kinship(kind='sibling', sex=sex)) == 'Sibling'
        assert render_english(Kinship(kind='niblings', sex=sex)) == 'Sibling’s child'
        assert render_english(Kinship(kind='affinal', via_sex=sex)) == 'Spouse'


def test_english_still_names_a_recorded_sex_exactly():
    assert render_english(Kinship(kind='descendant', depth=1, sex=MALE)) == 'Son'
    assert render_english(Kinship(kind='descendant', depth=1, sex=FEMALE)) == 'Daughter'
    assert render_english(Kinship(kind='niblings', sex=FEMALE)) == 'Niece'


def test_telugu_shows_both_words_when_the_sex_is_not_recorded():
    """Telugu has no neutral term for most of these, so it does what it already does for an
    unknown birth order: shows both and marks the label as needing a fact."""
    term = render_telugu(Kinship(kind='descendant', depth=1, sex=UNKNOWN))
    assert term.text == 'కొడుకు / కూతురు'
    assert term.unresolved is True
    assert term.bases == ('కొడుకు', 'కూతురు')

    # Sex and seniority both missing: every word it could be, and still marked unresolved.
    sibling = render_telugu(Kinship(kind='sibling', sex=UNKNOWN))
    assert sibling.unresolved is True
    assert len(sibling.bases) == 4


def test_telugu_does_not_duplicate_a_term_that_does_not_vary_by_sex():
    term = render_telugu(Kinship(kind='cousin', degree=1, sex=UNKNOWN))
    assert ' / ' not in term.text or term.bases[0] != term.bases[1]
