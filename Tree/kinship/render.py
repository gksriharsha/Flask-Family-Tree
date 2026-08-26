"""Turn a Kinship struct into words.

English and Telugu are separate functions, not two columns of one table. Telugu selects on
side first, then seniority, then sex, and treats parallel cousins as siblings — so a lookup
table keyed on English labels cannot reach it. That asymmetry is the reason the engine keeps
relationships as structs and leaves naming until last.
"""

from __future__ import annotations

from dataclasses import dataclass

from Tree.kinship.model import FEMALE, MALE, Kinship

ORDINALS = ['', 'First', 'Second', 'Third', 'Fourth', 'Fifth', 'Sixth']
TIMES = ['', 'once', 'twice', 'three times']


def _ordinal(n: int) -> str:
    return ORDINALS[n] if 0 <= n < len(ORDINALS) else f'{n}th'


def _times(n: int) -> str:
    return TIMES[n] if 0 <= n < len(TIMES) else f'{n} times'


def _greats(n: int) -> str:
    return 'Great-' * n if n > 0 else ''


# ── English ─────────────────────────────────────────────────────────────────────
def render_english(k: Kinship) -> str:
    """English never needs a birth order, so a missing one costs it nothing: it falls back
    to the base term — "Brother", "Father's brother"."""
    if k.kind == 'self':
        return 'This is you'
    if k.kind == 'none':
        return 'No recorded blood relation'

    male = k.sex == MALE
    adopt = ' (adoptive)' if k.adoptive else ''

    if k.kind == 'affinal':
        if k.via is None or k.via.kind == 'self':
            return 'Husband' if k.via_sex == MALE else 'Wife'
        suffix = '’s husband' if k.via_sex == MALE else '’s wife'
        return render_english(k.via) + suffix

    if k.kind == 'ancestor':
        if k.depth == 1:
            return ('Father' if male else 'Mother') + adopt
        if k.depth == 2:
            side = 'Paternal ' if k.side == 'paternal' else 'Maternal '
            return side + ('grandfather' if male else 'grandmother') + adopt
        return _greats(k.depth - 2) + ('grandfather' if male else 'grandmother') + adopt

    if k.kind == 'descendant':
        if k.depth == 1:
            return ('Son' if male else 'Daughter') + adopt
        if k.depth == 2:
            return ('Grandson' if male else 'Granddaughter') + adopt
        return _greats(k.depth - 2) + ('grandson' if male else 'granddaughter') + adopt

    if k.kind == 'sibling':
        noun = 'brother' if male else 'sister'
        if k.elder is None:
            return noun.capitalize() + adopt
        return ('Elder ' if k.elder else 'Younger ') + noun + adopt

    if k.kind == 'parent_sibling':
        if k.generations_up > 0:
            return _greats(k.generations_up - 1) + ('Granduncle' if male else 'Grandaunt') + adopt
        parent = 'Father' if k.link_sex == MALE else 'Mother'
        rank = '' if k.elder is None else ('elder ' if k.elder else 'younger ')
        return f'{parent}’s {rank}' + ('brother' if male else 'sister') + adopt

    if k.kind == 'niblings':
        if k.generations_down > 0:
            base = 'Grandnephew' if male else 'Grandniece'
            return _greats(k.generations_down - 1) + base + adopt
        return ('Nephew' if male else 'Niece') + adopt

    if k.kind == 'cousin':
        label = f'{_ordinal(k.degree)} cousin'
        if k.removal:
            label += f' {_times(k.removal)} removed'
        return label + adopt

    return '—'


def explain(k: Kinship) -> str:
    """Why the label is what it is. Never returns an empty sentence."""
    if k.kind == 'self':
        return 'Everything is measured from here.'
    if k.kind == 'none':
        return 'No common ancestor within the search depth.'
    if k.kind == 'affinal':
        if k.via is None or k.via.kind == 'self':
            return 'Married to you — an affinal link, not a blood one.'
        spouse = 'husband' if k.via_sex == MALE else 'wife'
        return (f'Related by marriage: {render_english(k.via).lower()} is the blood '
                f'relative, and this is their {spouse}.')

    bits: list[str] = []
    if k.kind == 'ancestor':
        bits.append('one generation above you' if k.depth == 1
                    else f'{k.depth} generations above you')
    if k.kind == 'descendant':
        bits.append('one generation below you' if k.depth == 1
                    else f'{k.depth} generations below you')
    if k.kind == 'sibling':
        bits.append('you share a parent')
    if k.kind == 'parent_sibling':
        bits.append('sibling of your ' + ('father' if k.link_sex == MALE else 'mother'))
    if k.kind == 'niblings':
        bits.append('child of your ' + ('brother' if k.link_sex == MALE else 'sister'))
    if k.kind == 'cousin':
        bits.append(f'common ancestor {k.degree + 1} generations up')
        bits.append('parallel cousin — the two linking parents are the same sex, which is '
                    'why Telugu uses a sibling term' if k.parallel else
                    'cross cousin — the linking parents are opposite sexes, so Telugu uses a '
                    'distinct, marriageable-kin term')
        if k.removal:
            bits.append(f'removed {_times(k.removal)}')
    if k.side and k.side != 'na':
        bits.append(f'{k.side} side')
    if k.elder is True:
        bits.append('elder than you')
    elif k.elder is False:
        bits.append('younger than you')
    elif k.elder is None and k.kind not in ('ancestor', 'descendant'):
        bits.append('birth order not recorded')
    if k.adoptive:
        bits.append('the route passes through an adoptive link')
    if not bits:
        return 'A direct link in the record.'
    return ' · '.join(bits) + '.'


# ── Telugu ──────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Term:
    """A rendered term. ``unresolved`` means the record cannot choose between ``options``."""

    text: str
    roman: str = ''
    gloss: str = ''
    unresolved: bool = False
    #: the base forms this term was built from, before any vocabulary or pin was applied
    bases: tuple[str, ...] = ()
    #: equivalent words for the same relation
    alternatives: tuple[dict, ...] = ()
    pinned: bool = False


def _t(text: str, roman: str, gloss: str) -> Term:
    return Term(text=text, roman=roman, gloss=gloss, bases=(text,))


def _pair(t1: str, r1: str, t2: str, r2: str, gloss: str) -> Term:
    """Telugu needs a seniority the record does not hold: show both, and say so."""
    return Term(text=f'{t1} / {t2}', roman=f'{r1} / {r2}', gloss=gloss,
                unresolved=True, bases=(t1, t2))


def render_telugu(k: Kinship) -> Term:
    if k.kind == 'self':
        return _t('నేను', 'Nenu', 'me')
    if k.kind == 'none':
        return _t('—', '', 'no recorded relation')

    male = k.sex == MALE

    if k.kind == 'affinal':
        via = k.via
        if via is None or via.kind == 'self':
            return (_t('భర్త', 'Bhartha', 'husband') if k.via_sex == MALE
                    else _t('భార్య', 'Bhaarya', 'wife'))
        paternal_uncle = (via.kind == 'parent_sibling' and via.side == 'paternal'
                          and via.link_sex == MALE and via.sex == MALE)
        if paternal_uncle:
            if via.elder is None:
                return _pair('పెద్దమ్మ', 'Peddamma',
                             'పిన్ని', 'Pinni',
                             'depends whether her husband is older than your father')
            return (_t('పెద్దమ్మ', 'Peddamma', 'father’s elder brother’s wife')
                    if via.elder
                    else _t('పిన్ని', 'Pinni', 'father’s younger brother’s wife'))
        if via.kind == 'parent_sibling' and via.sex == FEMALE and k.via_sex == MALE:
            parent = 'father' if via.link_sex == MALE else 'mother'
            return _t('మామయ్య', 'Maamayya',
                      f'{parent}’s sister’s husband')
        if via.kind == 'sibling' and via.sex == MALE and k.via_sex == FEMALE:
            if via.elder is None:
                return _pair('వదిన', 'Vadina', 'మరదలు',
                             'Maradalu', 'depends who is older')
            return (_t('వదిన', 'Vadina', 'elder brother’s wife') if via.elder
                    else _t('మరదలు', 'Maradalu', 'younger brother’s wife'))
        if via.kind == 'sibling' and via.sex == FEMALE and k.via_sex == MALE:
            if via.elder is None:
                return _pair('బావ', 'Baava', 'మరిది',
                             'Maridi', 'depends who is older')
            return (_t('బావ', 'Baava', 'elder sister’s husband') if via.elder
                    else _t('మరిది', 'Maridi', 'younger sister’s husband'))
        inner = render_telugu(via)
        suffix = ('భర్త', 'bhartha', 'husband') if k.via_sex == MALE \
            else ('భార్య', 'bhaarya', 'wife')
        return _t(f'{inner.text} {suffix[0]}', f'{inner.roman} {suffix[1]}',
                  f'{inner.gloss}’s {suffix[2]}')

    if k.kind == 'ancestor':
        if k.depth == 1:
            return (_t('నాన్న', 'Naanna', 'father') if male
                    else _t('అమ్మ', 'Amma', 'mother'))
        if k.depth == 2:
            if male:
                return _t('తాత', 'Thaatha', f'{k.side} grandfather')
            return (_t('నానమ్మ', 'Nanamma', 'father’s mother')
                    if k.side == 'paternal'
                    else _t('అమ్మమ్మ', 'Ammamma', 'mother’s mother'))
        return (_t('ముత్తాత', 'Muthaatha', 'great-grandfather') if male
                else _t('ముత్తవ్వ', 'Muthavva', 'great-grandmother'))

    if k.kind == 'descendant':
        if k.depth == 1:
            return (_t('కొడుకు', 'Koduku', 'son') if male
                    else _t('కూతురు', 'Kuthuru', 'daughter'))
        return (_t('మనవడు', 'Manavadu', 'grandson') if male
                else _t('మనవరాలు', 'Manavaralu', 'granddaughter'))

    # a parallel cousin a generation off takes parent's-sibling or child-of-sibling terms,
    # never the cross-cousin (marriageable-kin) words
    if k.kind == 'cousin' and k.parallel and k.removal > 0:
        if k.up:
            if male:
                if k.elder_than_link is None:
                    return _pair('పెద్దనాన్న', 'Peddananna',
                                 'చిన్నాన్న', 'Chinnanna',
                                 'depends which is older than your parent')
                return (_t('పెద్దనాన్న', 'Peddananna',
                           'parallel uncle, elder than your parent') if k.elder_than_link
                        else _t('చిన్నాన్న', 'Chinnanna',
                                'parallel uncle, younger than your parent'))
            return _t('అత్త', 'Attha', 'parallel aunt')
        return (_t('కొడుకు', 'Koduku', 'parallel nephew, addressed as a son')
                if male else
                _t('కూతురు', 'Kuthuru', 'parallel niece, addressed as a daughter'))

    # parallel cousins take sibling terms — the fact English erases
    if k.kind == 'sibling' or (k.kind == 'cousin' and k.parallel and k.removal == 0):
        if k.elder is None:
            return (_pair('అన్నయ్య', 'Annayya',
                          'తమ్ముడు', 'Thammudu', 'depends who is older')
                    if male else
                    _pair('అక్క', 'Akka', 'చెల్లి',
                          'Chelli', 'depends who is older'))
        if male:
            return (_t('అన్నయ్య', 'Annayya', 'elder brother') if k.elder
                    else _t('తమ్ముడు', 'Thammudu', 'younger brother'))
        return (_t('అక్క', 'Akka', 'elder sister') if k.elder
                else _t('చెల్లి', 'Chelli', 'younger sister'))

    if k.kind == 'parent_sibling':
        if k.generations_up > 0:
            # Telugu extends the grandparent terms to a grandparent's siblings
            if male:
                return _t('తాత', 'Thaatha',
                          'grandparent’s brother, addressed as grandfather')
            return (_t('నానమ్మ', 'Nanamma', 'grandparent’s sister')
                    if k.side == 'paternal'
                    else _t('అమ్మమ్మ', 'Ammamma', 'grandparent’s sister'))
        if k.link_sex == MALE:
            if male:
                if k.elder is None:
                    return _pair('పెద్దనాన్న', 'Peddananna',
                                 'చిన్నాన్న', 'Chinnanna',
                                 'depends whether he is older than your father')
                return (_t('పెద్దనాన్న', 'Peddananna',
                           'father’s elder brother') if k.elder
                        else _t('చిన్నాన్న', 'Chinnanna',
                                'father’s younger brother'))
            return _t('అత్త', 'Attha', 'father’s sister')
        if male:
            return _t('మామయ్య', 'Maamayya', 'mother’s brother')
        if k.elder is None:
            return _pair('పెద్దమ్మ', 'Peddamma',
                         'పిన్ని', 'Pinni',
                         'depends whether she is older than your mother')
        return (_t('పెద్దమ్మ', 'Peddamma', 'mother’s elder sister')
                if k.elder else _t('పిన్ని', 'Pinni', 'mother’s younger sister'))

    if k.kind == 'niblings':
        if k.generations_down > 0:
            return (_t('మనవడు', 'Manavadu', 'sibling’s grandson') if male
                    else _t('మనవరాలు', 'Manavaralu', 'sibling’s granddaughter'))
        via = 'brother' if k.link_sex == MALE else 'sister'
        if k.parallel:
            return (_t('కొడుకు', 'Koduku',
                       f'{via}’s son, addressed as a son') if male
                    else _t('కూతురు', 'Kuthuru',
                            f'{via}’s daughter, addressed as a daughter'))
        return (_t('మేనల్లుడు', 'Menalludu', f'{via}’s son')
                if male else
                _t('మేనకోడలు', 'Menakodalu', f'{via}’s daughter'))

    if k.kind == 'cousin':
        # cross cousins are marriageable kin and carry their own terms
        if k.elder is None:
            return (_pair('బావ', 'Baava', 'మరిది', 'Maridi',
                          'depends who is older') if male else
                    _pair('వదిన', 'Vadina', 'మరదలు',
                          'Maradalu', 'depends who is older'))
        if male:
            return (_t('బావ', 'Baava', 'elder cross-cousin') if k.elder
                    else _t('మరిది', 'Maridi', 'younger cross-cousin'))
        return (_t('వదిన', 'Vadina', 'elder cross-cousin') if k.elder
                else _t('మరదలు', 'Maradalu', 'younger cross-cousin'))

    return _t('—', '', '')
