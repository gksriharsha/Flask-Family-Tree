"""GEDCOM round-trip tests.

The interesting cases are the ones that usually get lost in translation: a within-family
adoption, a person whose sex is recorded as something 5.5.1 has no value for, and a birth
order that no date can express.
"""

import zipfile

import pytest

from Tree.gedcom import VERSION_7, VERSION_551, parse, render, to_document, write_gedzip
from Tree.kinship.model import (
    ADOPTIVE,
    FEMALE,
    MALE,
    FamilyGraph,
    ParentLink,
    Person,
    Union,
)


@pytest.fixture()
def graph() -> FamilyGraph:
    g = FamilyGraph()
    people = [
        (1, 'Aditya Varun', 'Varma', MALE, 1990, None),
        (2, 'Bharath Kiran', 'Varma', MALE, None, None),
        (3, 'Chandra Mohan', 'Varma', MALE, 1958, None),
        (4, 'Deepa Latha', 'Reddy', FEMALE, 1962, None),
        (5, 'Eshwar Datta', 'Varma', MALE, 1928, 2004),
        (6, 'Girija', 'Sharma', FEMALE, 1932, 2011),
        (7, 'Harinath', 'Sharma', MALE, None, None),
        (8, 'Parent1', 'Varma', MALE, 1901, 1974),
        (9, 'Parent2', 'Varma', FEMALE, 1905, 1981),
        (10, 'Anjali', 'Varma', 'intersex', 1996, None),
    ]
    for pid, given, surname, sex, born, died in people:
        g.add_person(Person(id=pid, given=given, surname=surname, sex=sex,
                            birth_year=born, death_year=died))
    for child, parent in [(1, 3), (1, 4), (2, 3), (2, 4), (10, 3), (10, 4),
                          (3, 5), (3, 6), (7, 5), (7, 6), (6, 8), (6, 9)]:
        g.add_parent_link(ParentLink(child_id=child, parent_id=parent))
    # the within-family adoption: born to 5+6, adopted by Girija's own parents
    g.add_parent_link(ParentLink(child_id=7, parent_id=8, role=ADOPTIVE))
    g.add_parent_link(ParentLink(child_id=7, parent_id=9, role=ADOPTIVE))
    for a, b in [(3, 4), (5, 6), (8, 9)]:
        g.add_union(Union(a_id=a, b_id=b))
    g.record_birth_order(elder_id=1, younger_id=2)
    return g


def test_a_seven_point_oh_file_is_well_formed(graph):
    text = render(to_document(graph), VERSION_7)
    assert text.startswith('0 HEAD\n')
    assert '2 VERS 7.0' in text
    assert text.endswith('0 TRLR\n')
    # 7.0 is always UTF-8 and forbids a character-set declaration
    assert '\n1 CHAR ' not in text
    # every level-0 record carries an xref except HEAD and TRLR
    for line in text.splitlines():
        if line.startswith('0 ') and not line.endswith(('HEAD', 'TRLR')):
            assert line.split()[1].startswith('@')


def test_five_five_one_declares_its_character_set_and_a_submitter(graph):
    text = render(to_document(graph), VERSION_551)
    assert '2 VERS 5.5.1' in text
    assert '1 CHAR UTF-8' in text
    assert '1 SUBM @U1@' in text and '0 @U1@ SUBM' in text
    assert '1 SCHMA' not in text          # 5.5.1 has nowhere to declare extensions


def test_a_sex_five_five_one_cannot_express_degrades_rather_than_lying(graph):
    seven = render(to_document(graph), VERSION_7)
    legacy = render(to_document(graph), VERSION_551)
    assert '1 SEX X' in seven             # 7.0 has a value for it
    assert '1 SEX X' not in legacy        # 5.5.1 does not, so it says "unknown"
    assert legacy.count('1 SEX U') >= 1


def test_the_within_family_adoption_survives_as_two_pedigrees(graph):
    text = render(to_document(graph), VERSION_7)
    block = text.split('0 @I7@ INDI')[1].split('\n0 ')[0]
    assert block.count('1 FAMC ') == 2
    assert '2 PEDI BIRTH' in block
    assert '2 PEDI ADOPTED' in block


def test_birth_order_travels_as_a_declared_extension(graph):
    text = render(to_document(graph), VERSION_7)
    assert '1 SCHMA' in text
    assert '2 TAG _ELDER ' in text
    assert '1 _ELDER @I2@' in text        # person 1 was born before person 2


def test_round_trip_preserves_people_and_links(graph):
    restored, _ = parse(render(to_document(graph), VERSION_7))
    assert len(restored.people) == len(graph.people)

    names = {p.full_name for p in restored.people.values()}
    assert 'Harinath Sharma' in names
    assert 'Deepa Latha Reddy' in names

    by_name = {p.full_name: p for p in restored.people.values()}
    assert by_name['Eshwar Datta Varma'].birth_year == 1928
    assert by_name['Eshwar Datta Varma'].death_year == 2004
    assert by_name['Anjali Varma'].sex == 'intersex'
    # a person with no recorded birth year keeps no birth year, rather than gaining one
    assert by_name['Harinath Sharma'].birth_year is None


def test_round_trip_preserves_the_adoption_roles(graph):
    restored, _ = parse(render(to_document(graph), VERSION_7))
    sitaramayya = next(p for p in restored.people.values() if p.given == 'Harinath')
    roles = {link.role for link in restored.parent_links(sitaramayya.id)}
    assert roles == {'biological', 'adoptive'}
    assert len(restored.parent_links(sitaramayya.id)) == 4


def test_round_trip_preserves_the_birth_order(graph):
    restored, _ = parse(render(to_document(graph), VERSION_7))
    by_name = {p.full_name: p for p in restored.people.values()}
    elder = by_name['Aditya Varun Varma'].id
    younger = by_name['Bharath Kiran Varma'].id
    assert restored.seniority(younger, elder) is True


def test_a_five_five_one_file_can_be_read_back(graph):
    restored, _ = parse(render(to_document(graph), VERSION_551))
    assert len(restored.people) == len(graph.people)


def test_gedzip_holds_the_file_at_the_documented_path(graph, tmp_path):
    archive = write_gedzip(to_document(graph), tmp_path / 'family.gdz')
    with zipfile.ZipFile(archive) as zipped:
        assert 'gedcom.ged' in zipped.namelist()
        text = zipped.read('gedcom.ged').decode('utf-8')
    assert '2 VERS 7.0' in text
    restored, _ = parse(text)
    assert len(restored.people) == len(graph.people)


def test_gedzip_carries_the_media_beside_the_file(graph, tmp_path):
    from Tree.gedcom.model import MediaObject
    media_root = tmp_path / 'store'
    (media_root / 'media').mkdir(parents=True)
    (media_root / 'media' / 'gathering.jpg').write_bytes(b'\xff\xd8not-a-real-jpeg')

    document = to_document(graph)
    document.media.append(MediaObject(xref='@O1@', path='media/gathering.jpg',
                                      title='Family gathering'))
    document.individuals[0].media.append('@O1@')

    archive = write_gedzip(document, tmp_path / 'family.gdz', media_root=media_root)
    with zipfile.ZipFile(archive) as zipped:
        assert set(zipped.namelist()) == {'gedcom.ged', 'media/gathering.jpg'}


def test_an_unknown_version_is_refused(graph):
    with pytest.raises(ValueError, match='Unsupported GEDCOM version'):
        render(to_document(graph), '6.0')


# ── importing a file ────────────────────────────────────────────────────────────
def test_gedzip_and_plain_text_both_read():
    """A .gdz is a zip with gedcom.ged at its root; a .ged is the text itself."""
    import io
    import zipfile

    from Tree.gedcom.store import read_gedcom_text

    text = '0 HEAD\n1 GEDC\n2 VERS 7.0\n0 @I1@ INDI\n1 NAME Ada /Varma/\n0 TRLR\n'
    assert read_gedcom_text(text.encode('utf-8'), 'family.ged') == text

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('gedcom.ged', text)
    assert read_gedcom_text(buffer.getvalue(), 'family.gdz') == text


def test_a_byte_order_mark_does_not_break_the_header():
    """5.5.1 files written on Windows very often carry one, and a stray BOM on line one makes
    the whole header unparseable."""
    from Tree.gedcom.store import read_gedcom_text

    text = '0 HEAD\n1 CHAR UTF-8\n0 TRLR\n'
    assert read_gedcom_text(b'\xef\xbb\xbf' + text.encode('utf-8'), 'f.ged').startswith('0 HEAD')


def test_an_archive_without_a_ged_is_refused():
    import io
    import zipfile

    import pytest

    from Tree.gedcom.store import read_gedcom_text

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('readme.txt', 'not a tree')
    with pytest.raises(ValueError, match=r'no \.ged'):
        read_gedcom_text(buffer.getvalue(), 'family.gdz')


def test_binary_rubbish_is_refused_rather_than_mangled():
    import pytest

    from Tree.gedcom.store import read_gedcom_text

    with pytest.raises(ValueError, match='not UTF-8'):
        read_gedcom_text(b'\xff\xfe\x00\x01\x02', 'family.ged')
