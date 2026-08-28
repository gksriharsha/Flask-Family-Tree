"""Dates that are allowed to be uncertain, and the ordering that follows from them."""

import pytest

from Tree.kinship.dates import (
    ABOUT,
    AFTER,
    BEFORE,
    BETWEEN,
    EXACT,
    UNKNOWN_DATE,
    YEAR,
    DateValue,
    compare,
)
from Tree.kinship.model import FamilyGraph, Person


@pytest.mark.parametrize(('text', 'mode', 'reads'), [
    ('1962-03-04', EXACT, '4 Mar 1962'),
    ('4 MAR 1962', EXACT, '4 Mar 1962'),
    ('MAR 1962', EXACT, 'Mar 1962'),
    ('1958', YEAR, '1958'),
    ('ABT 1955', ABOUT, 'about 1955'),
    ('ABOUT 1955', ABOUT, 'about 1955'),
    ('EST 1955', ABOUT, 'about 1955'),
    ('CAL 1955', ABOUT, 'about 1955'),
    ('BEF 1962', BEFORE, 'before 1962'),
    ('AFT 1950', AFTER, 'after 1950'),
    ('BET 1955 AND 1957', BETWEEN, 'between 1955 and 1957'),
])
def test_parses_the_forms_genealogy_actually_produces(text, mode, reads):
    parsed = DateValue.parse(text)
    assert parsed.mode == mode
    assert parsed.describe() == reads


@pytest.mark.parametrize('text', ['', None, 'sometime in the war', 'N/A'])
def test_unreadable_dates_become_unknown_rather_than_raising(text):
    """A tree must still load when one date is odd. Refusing the whole file over a single
    unparseable value would be a far worse failure than showing that value as unknown."""
    assert DateValue.parse(text).mode == 'unknown'


def test_gedcom_syntax_round_trips():
    for text in ('4 MAR 1962', '1958', 'ABT 1955', 'BEF 1962', 'AFT 1950',
                 'BET 1955 AND 1957'):
        assert DateValue.parse(text).gedcom() == text


def test_iso_dates_from_the_old_data_still_read():
    """Everything already in the graph is `yyyy-mm-dd`, including the placeholder."""
    assert DateValue.parse('1990-01-01').mode == EXACT
    assert DateValue.parse('1990-01-01').year == 1990


def test_intervals_bound_each_mode():
    assert DateValue(YEAR, year=1958).earliest.isoformat() == '1958-01-01'
    assert DateValue(YEAR, year=1958).latest.isoformat() == '1958-12-31'
    assert DateValue(ABOUT, year=1955).earliest.year == 1953
    assert DateValue(ABOUT, year=1955).latest.year == 1957
    # Open-ended on one side: a bound is evidence, and the other end is genuinely unknown.
    assert DateValue(BEFORE, year=1962).earliest is None
    assert DateValue(BEFORE, year=1962).latest.isoformat() == '1962-12-31'
    assert DateValue(AFTER, year=1950).earliest.isoformat() == '1950-01-01'
    assert DateValue(AFTER, year=1950).latest is None
    assert UNKNOWN_DATE.earliest is None and UNKNOWN_DATE.latest is None


def test_leap_day_is_a_real_date_and_a_non_leap_29_february_is_not():
    assert DateValue(EXACT, year=2020, month=2, day=29).latest.isoformat() == '2020-02-29'
    with pytest.raises(ValueError):
        DateValue(EXACT, year=2021, month=2, day=29)


def test_a_range_cannot_run_backwards():
    with pytest.raises(ValueError):
        DateValue(BETWEEN, year=1960, year2=1955)


def test_ordering_only_when_the_intervals_do_not_overlap():
    assert compare(DateValue(YEAR, year=1950), DateValue(YEAR, year=1960)) == -1
    assert compare(DateValue(YEAR, year=1960), DateValue(YEAR, year=1950)) == 1
    # Same year: nothing separates them, so nothing is claimed.
    assert compare(DateValue(YEAR, year=1950), DateValue(YEAR, year=1950)) is None
    # Overlapping approximations. This is the case the old bare-year comparison got wrong:
    # 1955 < 1956 looked decisive, when in truth either could be the elder.
    assert compare(DateValue(ABOUT, year=1955), DateValue(ABOUT, year=1956)) is None
    # Far enough apart that the windows clear each other.
    assert compare(DateValue(ABOUT, year=1950), DateValue(ABOUT, year=1960)) == -1
    # Bounds from opposite directions settle it without either date being known.
    assert compare(DateValue(BEFORE, year=1950), DateValue(AFTER, year=1960)) == -1
    assert compare(UNKNOWN_DATE, DateValue(YEAR, year=1950)) is None


def _two(birth_a, birth_b):
    graph = FamilyGraph()
    graph.add_person(Person(id=1, given='A', birth=birth_a))
    graph.add_person(Person(id=2, given='B', birth=birth_b))
    return graph


def test_seniority_uses_the_interval_not_a_midpoint():
    # seniority(x, y) answers "is y elder than x?"
    assert _two(DateValue(YEAR, year=1960), DateValue(YEAR, year=1950)).seniority(1, 2) is True
    assert _two(DateValue(YEAR, year=1950), DateValue(YEAR, year=1960)).seniority(1, 2) is False
    assert _two(DateValue(ABOUT, year=1955),
                DateValue(ABOUT, year=1956)).seniority(1, 2) is None


def test_a_remembered_birth_order_outranks_the_dates():
    """Someone who was there knows better than an approximation."""
    graph = _two(DateValue(YEAR, year=1950), DateValue(YEAR, year=1960))
    assert graph.seniority(1, 2) is False
    graph.record_birth_order(elder_id=2, younger_id=1)
    assert graph.seniority(1, 2) is True


def test_person_keeps_the_interval_and_the_plain_year_agreeing():
    """Two views of one fact. Letting them drift shows an age on one screen and a blank on
    the next."""
    from_year = Person(id=1, given='A', birth_year=1958)
    assert from_year.birth_date.mode == YEAR
    assert from_year.birth_date.year == 1958

    from_interval = Person(id=2, given='B', birth=DateValue(ABOUT, year=1955))
    assert from_interval.birth_year == 1955
    assert from_interval.birth_date.mode == ABOUT

    assert Person(id=3, given='C').birth_year is None
    assert Person(id=3, given='C').birth_date.is_known is False


def test_between_reports_a_midpoint_for_display_but_never_for_ordering():
    span = DateValue(BETWEEN, year=1950, year2=1960)
    assert span.sort_year == 1955
    # ...and yet it cannot be ordered against a date inside its own range.
    assert compare(span, DateValue(YEAR, year=1955)) is None


def test_payload_round_trips_through_the_interface_shape():
    for value in (DateValue(ABOUT, year=1955),
                  DateValue(BETWEEN, year=1950, year2=1960),
                  DateValue(EXACT, year=1962, month=3, day=4),
                  UNKNOWN_DATE):
        assert DateValue.from_payload(value.to_payload()) == value


def test_payload_rejects_a_mode_it_does_not_have():
    with pytest.raises(ValueError):
        DateValue.from_payload({'mode': 'circa-ish', 'year': 1955})
