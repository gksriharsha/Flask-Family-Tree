"""Write a Document as GEDCOM 7.0, GEDCOM 5.5.1, or GEDZIP.

Which dialect to reach for:

* **7.0** is the current standard and the one to keep as the durable copy: UTF-8 throughout,
  a real extension mechanism, and unambiguous dates.
* **5.5.1** is what most older desktop software still reads. The export degrades honestly —
  ``SEX X`` becomes ``U`` because 5.5.1 has no such value, and extension tags lose their
  schema declaration because 5.5.1 has nowhere to put one.
* **GEDZIP** (``.gdz``) is a 7.0 file and its media in one ZIP, which is what makes a tree
  with photographs portable as a single artifact.
"""

from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path

from Tree.gedcom.model import (
    SEX_7,
    SEX_551,
    VERSION_7,
    VERSION_551,
    Document,
    Line,
)

#: Extension tags, declared in a 7.0 SCHMA so a reader knows they are ours and not a clash.
EXTENSIONS = {
    '_ELDER': 'https://github.com/gksriharsha/Flask-Family-Tree/gedcom/ELDER',
}

PRODUCT = 'Flask-Family-Tree'


def _header(version: str, tree_name: str, when: datetime) -> list[Line]:
    lines = [Line(0, 'HEAD'), Line(1, 'GEDC'), Line(2, 'VERS', version)]
    if version == VERSION_551:
        # 5.5.1 requires a character-set declaration; 7.0 forbids one, because it is
        # always UTF-8.
        lines.append(Line(1, 'CHAR', 'UTF-8'))
    lines += [
        Line(1, 'SOUR', PRODUCT),
        Line(2, 'NAME', tree_name),
        Line(1, 'DATE', when.strftime('%d %b %Y').upper()),
        Line(2, 'TIME', when.strftime('%H:%M:%S')),
    ]
    if version == VERSION_7:
        lines.append(Line(1, 'SCHMA'))
        for tag, uri in EXTENSIONS.items():
            lines.append(Line(2, 'TAG', f'{tag} {uri}'))
    else:
        # 5.5.1 requires a submitter record to be pointed at from the header.
        lines.append(Line(1, 'SUBM', '@U1@'))
    return lines


def _individual(person, version: str) -> list[Line]:
    sex_map = SEX_7 if version == VERSION_7 else SEX_551
    name = f'{person.given} /{person.surname}/'.strip()
    lines = [Line(0, 'INDI', xref=person.xref), Line(1, 'NAME', name)]
    if person.given:
        lines.append(Line(2, 'GIVN', person.given))
    if person.surname:
        lines.append(Line(2, 'SURN', person.surname))
    lines.append(Line(1, 'SEX', sex_map.get(person.sex, 'U')))

    # An event with no date is still worth writing when the fact itself is known, but this
    # tree only records the date, so an unknown date means there is nothing to say.
    if person.birth.is_known:
        lines += [Line(1, 'BIRT'), Line(2, 'DATE', person.birth.gedcom())]
    if person.death.is_known:
        lines += [Line(1, 'DEAT'), Line(2, 'DATE', person.death.gedcom())]

    for family_xref, pedigree in person.child_of:
        lines.append(Line(1, 'FAMC', family_xref))
        # BIRTH is the default; stating it anyway keeps a within-family adoption legible,
        # because the point is that the OTHER link is not a birth link.
        lines.append(Line(2, 'PEDI', pedigree))
    for family_xref in person.spouse_in:
        lines.append(Line(1, 'FAMS', family_xref))
    for media_xref in person.media:
        lines.append(Line(1, 'OBJE', media_xref))

    # GEDCOM has no standard way to record that one person was born before another when
    # neither date is known. It is written as a declared extension rather than as a
    # fabricated date, and a reader that does not know the tag simply skips it.
    for younger in person.elder_than:
        lines.append(Line(1, '_ELDER', younger))
    return lines


def _family(family) -> list[Line]:
    lines = [Line(0, 'FAM', xref=family.xref)]
    if family.husband:
        lines.append(Line(1, 'HUSB', family.husband))
    if family.wife:
        lines.append(Line(1, 'WIFE', family.wife))
    # A union the record does not describe as husband-and-wife still needs its partners
    # naming, so they are emitted as ASSO rather than silently dropped.
    for partner in family.partners:
        if partner not in (family.husband, family.wife):
            lines += [Line(1, 'ASSO', partner), Line(2, 'ROLE', 'SPOU')]
    for child in family.children:
        lines.append(Line(1, 'CHIL', child))
    return lines


def _media(obj, version: str) -> list[Line]:
    lines = [Line(0, 'OBJE', xref=obj.xref), Line(1, 'FILE', obj.path)]
    if version == VERSION_7:
        lines.append(Line(2, 'FORM', obj.media_type))
    else:
        # 5.5.1 wants a bare extension in FORM, not a media type.
        lines.append(Line(2, 'FORM', Path(obj.path).suffix.lstrip('.').lower() or 'jpg'))
    if obj.title:
        lines.append(Line(2, 'TITL', obj.title))
    return lines


def render(document: Document, version: str = VERSION_7,
           when: datetime | None = None) -> str:
    """Render the whole document. Always ends with a newline, as the spec requires."""
    if version not in (VERSION_7, VERSION_551):
        raise ValueError(f'Unsupported GEDCOM version: {version}')
    when = when or datetime.now(timezone.utc)

    lines = _header(version, document.tree_name, when)
    if version == VERSION_551:
        lines += [Line(0, 'SUBM', xref='@U1@'), Line(1, 'NAME', PRODUCT)]
    for person in document.individuals:
        lines += _individual(person, version)
    for family in document.families:
        lines += _family(family)
    for obj in document.media:
        lines += _media(obj, version)
    lines.append(Line(0, 'TRLR'))

    return '\n'.join(line.render() for line in lines) + '\n'


def write_gedcom(document: Document, path: Path, version: str = VERSION_7,
                 when: datetime | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(document, version, when), encoding='utf-8', newline='\n')
    return path


def write_gedzip(document: Document, path: Path, media_root: Path | None = None,
                 when: datetime | None = None) -> Path:
    """Write a GEDZIP: a 7.0 file at ``gedcom.ged`` plus its media, in one archive.

    This is the format to hand someone when the tree has photographs, because a bare .ged
    only ever holds *paths* to media — send it on its own and every picture is a dead link.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('gedcom.ged', render(document, VERSION_7, when))
        if media_root is not None:
            for obj in document.media:
                source = Path(media_root) / obj.path
                if source.is_file():
                    archive.write(source, obj.path)
    return path
