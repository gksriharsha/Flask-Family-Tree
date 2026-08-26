"""A GEDCOM document as structure, independent of which version it will be written as.

GEDCOM 7.0 and 5.5.1 differ in the header, in a handful of tags, and in how long text is
continued — but they describe the same records. Building the records once and letting the
writer decide the dialect keeps the two exports honest with each other.
"""

from __future__ import annotations

from dataclasses import dataclass, field

VERSION_7 = '7.0'
VERSION_551 = '5.5.1'

#: GEDCOM pedigree values for how a child is linked to a family.
PEDIGREE = {
    'biological': 'BIRTH',
    'adoptive': 'ADOPTED',
    'foster': 'FOSTER',
    'step': 'OTHER',
    'guardian': 'OTHER',
}

#: 7.0 admits X (other) and U (unknown); 5.5.1 has no X, so it degrades to U.
SEX_7 = {'male': 'M', 'female': 'F', 'intersex': 'X', 'unknown': 'U'}
SEX_551 = {'male': 'M', 'female': 'F', 'intersex': 'U', 'unknown': 'U'}


@dataclass
class Line:
    level: int
    tag: str
    value: str = ''
    xref: str = ''

    def render(self) -> str:
        parts = [str(self.level)]
        if self.xref:
            parts.append(self.xref)
        parts.append(self.tag)
        if self.value:
            parts.append(self.value)
        return ' '.join(parts)


@dataclass
class Individual:
    xref: str
    given: str = ''
    surname: str = ''
    sex: str = 'unknown'
    birth_year: int | None = None
    death_year: int | None = None
    #: (family xref, pedigree) — a person can belong to more than one, which is exactly
    #: how a within-family adoption is represented.
    child_of: list[tuple[str, str]] = field(default_factory=list)
    spouse_in: list[str] = field(default_factory=list)
    #: xrefs of people this person was born before. GEDCOM has no standard way to say it.
    elder_than: list[str] = field(default_factory=list)
    media: list[str] = field(default_factory=list)


@dataclass
class Family:
    xref: str
    husband: str | None = None
    wife: str | None = None
    partners: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)


@dataclass
class MediaObject:
    xref: str
    #: path inside the archive, e.g. ``media/1962-gathering.jpg``
    path: str
    media_type: str = 'image/jpeg'
    title: str = ''


@dataclass
class Document:
    individuals: list[Individual] = field(default_factory=list)
    families: list[Family] = field(default_factory=list)
    media: list[MediaObject] = field(default_factory=list)
    tree_name: str = 'Family Tree'
