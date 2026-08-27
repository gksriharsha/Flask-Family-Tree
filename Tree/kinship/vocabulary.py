"""Which *word* a family uses for a relationship.

Kept apart from the engine on purpose. Working out that someone is your father's younger
brother is a fact about the graph; calling him చిన్నాన్న or కక్కయ్య or బాబాయి is a fact about
who is speaking. Swapping a word, or a whole regional vocabulary, therefore never touches a
single link in the data.

Three sources, in order of precedence:

    1. a pin on this particular person — "everyone calls this uncle బాబాయి"
    2. the vocabulary of the branch of the family currently speaking
    3. the default form

The built-in list is a starting point, not authority. Families add their own words as they
come across them, and those sit alongside the defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from Tree.kinship.render import Term

PATERNAL = 'paternal'
MATERNAL = 'maternal'


@dataclass(frozen=True)
class Variant:
    term: str
    roman: str = ''
    usage: str = ''
    added_by_family: bool = False


#: Forms in common use, offered as a starting point. `maternal` is a word that a maternal
#: branch commonly uses in place of the default; `also` are equivalents either side may use.
DEFAULT_VARIANTS: dict[str, dict] = {
    'చిన్నాన్న': {'maternal': Variant('కక్కయ్య', 'Kakkayya'),
                  'also': [Variant('బాబాయి', 'Babai', 'widely used'),
                           Variant('పినతండ్రి', 'Pinathandri', 'formal')]},
    'పెద్దనాన్న': {'also': [Variant('పెదనాన్న', 'Pedananna', 'shorter form'),
                            Variant('దొడ్డనాన్న', 'Doddananna', 'Rayalaseema')]},
    'మామయ్య': {'also': [Variant('మేనమామ', 'Menamama', 'more formal')]},
    'అత్త': {'also': [Variant('మేనత్త', 'Menattha', 'more formal')]},
    'పిన్ని': {'also': [Variant('చిన్నమ్మ', 'Chinnamma', 'widely used')]},
    'పెద్దమ్మ': {'also': [Variant('పెత్తల్లి', 'Pettalli', 'older form')]},
    'నానమ్మ': {'also': [Variant('నాయనమ్మ', 'Nayanamma', 'widely used')]},
    'తాత': {'also': [Variant('తాతయ్య', 'Thaathayya', 'affectionate')]},
    'అన్నయ్య': {'also': [Variant('అన్న', 'Anna', 'shorter form')]},
    'అక్క': {'also': [Variant('అక్కయ్య', 'Akkayya', 'affectionate')]},
    'చెల్లి': {'also': [Variant('చెల్లెలు', 'Chellelu', 'fuller form')]},
    'కొడుకు': {'also': [Variant('అబ్బాయి', 'Abbayi', 'everyday')]},
    'కూతురు': {'also': [Variant('అమ్మాయి', 'Ammayi', 'everyday')]},
}


@dataclass
class Vocabulary:
    """The words one family uses, and any pins onto individual people."""

    side: str = PATERNAL
    #: base term -> extra words this family has recorded
    added: dict[str, list[Variant]] = field(default_factory=dict)
    #: (person id, base term) -> the word always used for that person
    pins: dict[tuple[int, str], Variant] = field(default_factory=dict)

    # ---- editing ------------------------------------------------------------
    def add_word(self, base_term: str, term: str, roman: str = '', usage: str = '') -> Variant:
        """Record a word discovered from a relative. Returns the stored variant."""
        variant = Variant(term=term, roman=roman,
                          usage=usage or 'added by your family', added_by_family=True)
        bucket = self.added.setdefault(base_term, [])
        if not any(v.term == term for v in bucket):
            bucket.append(variant)
        return variant

    def pin(self, person_id: int, base_term: str, term: str, roman: str = '') -> None:
        """Always use ``term`` for this person, whatever the vocabulary says."""
        self.pins[(person_id, base_term)] = Variant(term=term, roman=roman)

    def unpin(self, person_id: int, base_terms) -> None:
        for base in base_terms:
            self.pins.pop((person_id, base), None)

    # ---- rendering ----------------------------------------------------------
    def apply(self, term: Term, person_id: int | None = None) -> Term:
        """Resolve a rendered term to the word this reader should see."""
        resolved = [self._resolve(base, person_id) for base in (term.bases or (term.text,))]

        text = ' / '.join(r['text'] for r in resolved)
        roman = ' / '.join(r['roman'] for r in resolved if r['roman'])
        alternatives: list[dict] = []
        for r in resolved:
            alternatives.extend(r['alternatives'])

        return replace(
            term,
            text=text,
            roman=roman or term.roman,
            alternatives=tuple(alternatives),
            pinned=any(r['pinned'] for r in resolved),
        )

    def _resolve(self, base: str, person_id: int | None) -> dict:
        entry = DEFAULT_VARIANTS.get(base, {})
        maternal: Variant | None = entry.get('maternal')
        pinned = self.pins.get((person_id, base)) if person_id is not None else None

        if self.side == MATERNAL and maternal is not None:
            default = Variant(maternal.term, maternal.roman)
        else:
            default = Variant(base, _roman_for(base))
        current = pinned or default

        pool: list[Variant] = []
        if maternal is not None:
            pool.append(
                Variant(base, _roman_for(base), 'father’s side of this family')
                if self.side == MATERNAL else
                Variant(maternal.term, maternal.roman, 'mother’s side of this family')
            )
        pool.extend(entry.get('also', []))
        pool.extend(self.added.get(base, []))
        if pinned is not None and pinned.term != default.term:
            pool.append(Variant(default.term, default.roman, 'the usual word'))

        return {
            'text': current.term,
            'roman': current.roman,
            'pinned': pinned is not None,
            'alternatives': [
                {'term': v.term, 'roman': v.roman, 'usage': v.usage,
                 'added_by_family': v.added_by_family, 'base': base}
                for v in pool if v.term != current.term
            ],
        }


#: Romanisations for the default forms, so an alternative can offer one too.
_ROMAN = {
    'నాన్న': 'Naanna', 'అమ్మ': 'Amma', 'తాత': 'Thaatha', 'నానమ్మ': 'Nanamma',
    'అమ్మమ్మ': 'Ammamma', 'ముత్తాత': 'Muthaatha', 'ముత్తవ్వ': 'Muthavva',
    'కొడుకు': 'Koduku', 'కూతురు': 'Kuthuru', 'మనవడు': 'Manavadu',
    'మనవరాలు': 'Manavaralu', 'అన్నయ్య': 'Annayya', 'తమ్ముడు': 'Thammudu',
    'అక్క': 'Akka', 'చెల్లి': 'Chelli', 'పెద్దనాన్న': 'Peddananna',
    'చిన్నాన్న': 'Chinnanna', 'అత్త': 'Attha', 'మామయ్య': 'Maamayya',
    'పెద్దమ్మ': 'Peddamma', 'పిన్ని': 'Pinni', 'మేనల్లుడు': 'Menalludu',
    'మేనకోడలు': 'Menakodalu', 'బావ': 'Baava', 'మరిది': 'Maridi',
    'వదిన': 'Vadina', 'మరదలు': 'Maradalu', 'భర్త': 'Bhartha', 'భార్య': 'Bhaarya',
    'నేను': 'Nenu',
}


def _roman_for(term: str) -> str:
    return _ROMAN.get(term, '')
