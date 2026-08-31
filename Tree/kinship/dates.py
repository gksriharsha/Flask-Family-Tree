"""Dates that are allowed to be uncertain.

Genealogy almost never yields a clean ``yyyy-mm-dd``. It yields "about 1955", "before the
1962 photograph", "somewhere between these two documents", or nothing at all. The previous
model held a bare ``birth_year: int``, which forced every one of those into either a lie or a
blank -- and a blank loses the evidence that a bound actually represents.

Every date here is an **interval**: an earliest possible day and a latest possible day, either
of which may be open. That single idea covers all seven ways a date gets recorded, and it is
what makes comparison honest -- two dates can be ordered only when their intervals do not
overlap. "About 1955" and "about 1956" overlap, so neither is provably elder, and the engine
says so rather than inventing a rank from the midpoints.

The stored form is GEDCOM date syntax (``ABT 1955``, ``BET 1955 AND 1957``, ``4 MAR 1962``).
That needs no new property in the graph, and it is what the tree's ``family.ged`` wants
anyway, so nothing has to be translated on the way out.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date

#: A document gives the day.
EXACT = 'exact'
#: A year is known but the month and day are not.
YEAR = 'year'
#: Somewhere near a year, not pinned to it.
ABOUT = 'about'
#: Known to be no later than a year.
BEFORE = 'before'
#: Known to be no earlier than a year.
AFTER = 'after'
#: Bounded on both sides, usually by two different documents.
BETWEEN = 'between'
#: Nothing is known. An honest gap, not a placeholder.
UNKNOWN = 'unknown'

MODES = (EXACT, YEAR, ABOUT, BEFORE, AFTER, BETWEEN, UNKNOWN)

#: How far either side of the stated year "about" is taken to reach. Two years is the
#: convention most genealogy software settles on, and the exact figure matters less than
#: the fact that it is a stated interval rather than a hidden guess.
ABOUT_SLACK = 2

MONTHS = ('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
          'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC')

MIN_YEAR, MAX_YEAR = 1, 9999


def _clamp_year(value: int) -> int:
    return max(MIN_YEAR, min(MAX_YEAR, value))


def _end_of(year: int, month: int | None = None) -> date:
    """Last representable day of a year, or of a month within it."""
    year = _clamp_year(year)
    if month is None:
        return date(year, 12, 31)
    return date(year, month, calendar.monthrange(year, month)[1])


@dataclass(frozen=True)
class DateValue:
    """One recorded date, at whatever precision it was actually recorded.

    ``year2`` is only meaningful for :data:`BETWEEN`. ``month`` and ``day`` are only
    meaningful for :data:`EXACT`, and even there the day may be absent -- a record that gives
    "March 1962" is more precise than a year and less precise than a day, and squashing it
    to either would be a loss.
    """

    mode: str = UNKNOWN
    year: int | None = None
    month: int | None = None
    day: int | None = None
    year2: int | None = None

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f'Unknown date mode: {self.mode!r}')
        if self.mode != UNKNOWN and self.year is None:
            raise ValueError(f'A {self.mode} date needs a year.')
        if self.mode == BETWEEN:
            if self.year2 is None:
                raise ValueError('A between date needs both years.')
            if self.year2 < self.year:
                raise ValueError('The later year of a range cannot precede the earlier one.')
        if self.month is not None and not 1 <= self.month <= 12:
            raise ValueError(f'Month out of range: {self.month}')
        if self.day is not None:
            if self.month is None:
                raise ValueError('A day needs a month.')
            try:
                date(_clamp_year(self.year or 1), self.month, self.day)
            except ValueError as exc:
                raise ValueError(f'No such date: {exc}') from exc

    # ── the interval ────────────────────────────────────────────────────────────
    @property
    def earliest(self) -> date | None:
        """First day this date could be. None means unbounded in the past."""
        if self.mode in (UNKNOWN, BEFORE):
            return None
        year = _clamp_year(self.year)
        if self.mode == ABOUT:
            return date(_clamp_year(year - ABOUT_SLACK), 1, 1)
        if self.mode == EXACT:
            return date(year, self.month or 1, self.day or 1)
        return date(year, 1, 1)

    @property
    def latest(self) -> date | None:
        """Last day this date could be. None means unbounded in the future."""
        if self.mode in (UNKNOWN, AFTER):
            return None
        year = _clamp_year(self.year)
        if self.mode == ABOUT:
            return _end_of(year + ABOUT_SLACK)
        if self.mode == BETWEEN:
            return _end_of(self.year2)
        if self.mode == EXACT:
            if self.day is not None:
                return date(year, self.month, self.day)
            return _end_of(year, self.month)
        return _end_of(year)

    @property
    def is_known(self) -> bool:
        return self.mode != UNKNOWN

    @property
    def sort_year(self) -> int | None:
        """A single year for display and rough ordering only.

        Never use this to decide seniority -- that is what :func:`compare` is for. A midpoint
        looks like a fact and is not one.
        """
        if self.mode == UNKNOWN:
            return None
        if self.mode == BETWEEN:
            return (self.year + self.year2) // 2
        return self.year

    # ── text ────────────────────────────────────────────────────────────────────
    def gedcom(self) -> str:
        """GEDCOM date syntax. This is also the form stored in the graph."""
        if self.mode == UNKNOWN:
            return ''
        if self.mode == EXACT:
            parts = []
            if self.day is not None:
                parts.append(str(self.day))
            if self.month is not None:
                parts.append(MONTHS[self.month - 1])
            parts.append(str(self.year))
            return ' '.join(parts)
        if self.mode == YEAR:
            return str(self.year)
        if self.mode == ABOUT:
            return f'ABT {self.year}'
        if self.mode == BEFORE:
            return f'BEF {self.year}'
        if self.mode == AFTER:
            return f'AFT {self.year}'
        return f'BET {self.year} AND {self.year2}'

    def describe(self) -> str:
        """How the record reads, in words, for the interface."""
        if self.mode == UNKNOWN:
            return 'unknown'
        if self.mode == EXACT:
            if self.day is not None:
                return f'{self.day} {MONTHS[self.month - 1].title()} {self.year}'
            if self.month is not None:
                return f'{MONTHS[self.month - 1].title()} {self.year}'
            return str(self.year)
        if self.mode == YEAR:
            return str(self.year)
        if self.mode == ABOUT:
            return f'about {self.year}'
        if self.mode == BEFORE:
            return f'before {self.year}'
        if self.mode == AFTER:
            return f'after {self.year}'
        return f'between {self.year} and {self.year2}'

    # ── parsing ─────────────────────────────────────────────────────────────────
    _ISO = re.compile(r'^(\d{3,4})-(\d{1,2})(?:-(\d{1,2}))?$')
    _BETWEEN = re.compile(r'^BET(?:WEEN)?\s+(\d{1,4})\s+AND\s+(\d{1,4})$', re.I)
    _MODIFIED = re.compile(r'^(ABT|ABOUT|CAL|EST|BEF|BEFORE|AFT|AFTER)\s+(.+)$', re.I)
    _DMY = re.compile(r'^(?:(\d{1,2})\s+)?([A-Z]{3,})\s+(\d{1,4})$', re.I)
    _YEAR_ONLY = re.compile(r'^(\d{1,4})$')

    @classmethod
    def parse(cls, text: object) -> DateValue:
        """Read a stored or imported date. Anything unrecognised becomes UNKNOWN.

        Deliberately forgiving: this reads values written by other genealogy programs and by
        earlier versions of this one. A date that cannot be understood is reported as absent
        rather than raising, because refusing to load a tree over one odd date would be a far
        worse failure than showing that one date as unknown.
        """
        if isinstance(text, DateValue):
            return text
        if isinstance(text, (list, tuple, set)):
            for item in text:
                parsed = cls.parse(item)
                if parsed.is_known:
                    return parsed
            return UNKNOWN_DATE
        if text is None:
            return UNKNOWN_DATE
        raw = str(text).strip()
        if not raw:
            return UNKNOWN_DATE

        match = cls._BETWEEN.match(raw)
        if match:
            low, high = int(match.group(1)), int(match.group(2))
            if high < low:
                low, high = high, low
            return cls(BETWEEN, year=low, year2=high)

        match = cls._MODIFIED.match(raw)
        if match:
            keyword = match.group(1).upper()
            inner = cls.parse(match.group(2))
            if not inner.is_known:
                return UNKNOWN_DATE
            mode = {'BEF': BEFORE, 'BEFORE': BEFORE,
                    'AFT': AFTER, 'AFTER': AFTER}.get(keyword, ABOUT)
            return cls(mode, year=inner.year)

        match = cls._ISO.match(raw)
        if match:
            year, month = int(match.group(1)), int(match.group(2))
            day = int(match.group(3)) if match.group(3) else None
            try:
                return cls(EXACT, year=year, month=month, day=day)
            except ValueError:
                return cls(YEAR, year=year)

        match = cls._DMY.match(raw)
        if match:
            token = match.group(2).upper()[:3]
            if token in MONTHS:
                day = int(match.group(1)) if match.group(1) else None
                try:
                    return cls(EXACT, year=int(match.group(3)),
                               month=MONTHS.index(token) + 1, day=day)
                except ValueError:
                    return cls(YEAR, year=int(match.group(3)))

        match = cls._YEAR_ONLY.match(raw)
        if match:
            return cls(YEAR, year=int(match.group(1)))

        # Last resort: a leading four-digit year inside something else entirely.
        leading = re.match(r'^(\d{4})', raw)
        if leading:
            return cls(YEAR, year=int(leading.group(1)))
        return UNKNOWN_DATE

    @classmethod
    def from_payload(cls, payload: object) -> DateValue:
        """Build from the interface's JSON: ``{mode, year, month, day, year2}``."""
        if payload is None:
            return UNKNOWN_DATE
        if isinstance(payload, str):
            return cls.parse(payload)
        if not isinstance(payload, dict):
            raise ValueError('A date must be an object or a string.')
        mode = str(payload.get('mode') or UNKNOWN).strip().lower()
        if mode not in MODES:
            raise ValueError(f'mode must be one of: {", ".join(MODES)}')
        if mode == UNKNOWN:
            return UNKNOWN_DATE

        def number(key: str) -> int | None:
            value = payload.get(key)
            if value is None or value == '':
                return None
            try:
                return int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f'{key} must be a whole number.') from exc

        return cls(mode, year=number('year'), month=number('month'),
                   day=number('day'), year2=number('year2'))

    def to_payload(self) -> dict:
        return {'mode': self.mode, 'year': self.year, 'month': self.month,
                'day': self.day, 'year2': self.year2,
                'reads': self.describe(), 'gedcom': self.gedcom()}


UNKNOWN_DATE = DateValue()


def compare(a: DateValue, b: DateValue) -> int | None:
    """Order two dates, or admit that they cannot be ordered.

    Returns -1 when *a* is certainly earlier, 1 when it is certainly later, and ``None`` when
    the intervals overlap so that neither can be proved. ``None`` is the common answer and is
    the whole point: it is what stops the interface inventing a birth order.
    """
    if not a.is_known or not b.is_known:
        return None
    if a.latest is not None and b.earliest is not None and a.latest < b.earliest:
        return -1
    if b.latest is not None and a.earliest is not None and b.latest < a.earliest:
        return 1
    return None
