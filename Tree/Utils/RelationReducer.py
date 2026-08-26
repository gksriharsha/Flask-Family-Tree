"""Fold a chain of edge labels into a single relation label.

Mechanical defects fixed here. The composition table itself is unchanged, and it is *not*
correct -- it cannot express cousin degree or removal, it maps grandparent-plus-sibling onto
"grandfather", and it has no entry for parent-then-child, so the most common relationship in any
family renders as the compound "Father's Son". Replacing it needs a real kinship algorithm
(nearest common ancestor, then a canonical struct, then per-locale rendering), which is a
separate piece of work. These fixes stop it from crashing and from leaking internals.
"""

import logging

log = logging.getLogger(__name__)


def _clean(label):
    return str(label).replace('*', '')


def reduce(relation_sequence):
    """Reduce a label chain to as few labels as the table allows. Always returns a list."""
    parse = list(relation_sequence or [])
    if not parse:
        # Used to return [None], which then reached callers as a relation label.
        return []
    if len(parse) == 1:
        # The loop started at index 1, so a single-element chain was discarded entirely and the
        # function returned [None] -- meaning a one-hop relationship had no answer.
        return [_clean(parse[0])]

    relation = []
    previous = _clean(parse[0])
    for current in parse[1:]:
        try:
            previous = relation_definition(previous, _clean(current), relation_language='English')
        except KeyError:
            relation.append(previous)
            # The original assigned the raw label here, so the '*' adoption marker leaked
            # through to the user while every other path stripped it.
            previous = _clean(current)
    relation.append(previous)
    return relation


def relation_definition(previous, current, relation_language='Telugu'):
    if relation_language == 'Telugu':
        # Retained as documentation of intent, but unreachable in practice and unreachable in
        # principle: the keys are Telugu kinship terms while the inputs are English edge
        # labels, so the first lookup raises KeyError. A composition table cannot be localised
        # -- Telugu distinguishes maternal from paternal kin lexically, which needs the path's
        # side, and a fold over labels has already discarded it.
        relation = {'Naanna': {'Naanna': 'Thaatha', 'Amma': 'Maamma', 'Thammudu': 'Chinnaanna',
                               'Annayya': 'Peddanaanna', 'Akka': 'Attha', 'Chelli': 'Attha',
                               'Kuthuru': 'Chelli'},
                    'Thaatha': {'Thammudu': 'Thaatha', 'Anna': 'Thaatha',
                                'Koduku': 'Baabayya', 'Kuthuru': 'Attha'},
                    'Attha': {'Koduku': 'Baava', 'Kuthuru': 'Vadina', 'Bhartha': 'Maavayya'},
                    'Baava': {'Bhaarya': 'Akka'},
                    'Vadina': {'Bhartha': 'Anna'},
                    'Akka': {'Akka': 'Akka', 'Annayya': 'Annayya'},
                    'Annayya': {'Annayya': 'Annayya', 'Akka': 'Akka'}
                    }
    else:
        relation = {
            'Father_Of': {'Father_Of': 'Grandfather_Of',
                          'Brother_Of': 'Uncle_Of',
                          'Sister_Of': 'Aunt_Of',
                          'Mother_Of': 'Grandmother_Of'
                          },
            'Mother_Of': {'Father_Of': 'Grandfather_Of',
                          'Brother_Of': 'Uncle_Of',
                          'Sister_Of': 'Aunt_Of',
                          'Mother_Of': 'Grandmother_Of'
                          },
            'Brother_Of': {'Wife_Of': 'Sister in law_Of',
                           'Son_Of': 'Nephew_Of',
                           'Daughter_Of': 'Niece_Of'
                           },
            'Sister_Of': {'Son_Of': 'Nephew_Of',
                          'Husband_Of': 'Brother in law_Of',
                          'Daughter_Of': 'Niece_Of'},
            'Husband_Of': {'Father_Of': 'Father in law_Of',
                           'Mother_Of': 'Mother in law_Of',
                           'Brother_Of': 'Brother in law_Of',
                           'Sister_Of': 'Sister in law_Of'
                           },
            'Wife_Of': {'Father_Of': 'Father in law_Of',
                        'Mother_Of': 'Mother in law_Of',
                        'Brother_Of': 'Brother in law_Of',
                        'Sister_Of': 'Sister in law_Of',
                        },
            'Son_Of': {'Son_Of': 'Grandson_Of',
                       'Daughter_Of': 'Granddaughter_Of',
                       'Wife_Of': 'Daughter in law_Of',
                       },
            'Daughter_Of': {'Husband_Of': 'Son in law_Of',
                            'Son_Of': 'Grandson_Of',
                            'Daughter_Of': 'Granddaughter_Of',
                            },
            'Grandfather_Of': {'Brother_Of': 'Grandfather_Of',
                               'Sister_Of': 'Grandmother_Of',
                               'Son_Of': 'Uncle_Of',
                               'Daughter_Of': 'Aunt_Of'
                               },
            'Grandmother_Of': {'Brother_Of': 'Grandfather_Of',
                               'Sister_Of': 'Grandmother_Of',
                               'Son_Of': 'Uncle_Of',
                               'Daughter_Of': 'Aunt_Of'},
            'Uncle_Of': {'Son_Of': 'Cousin_Of',
                         'Daughter_Of': 'Cousin_Of',
                         'Brother_Of': 'Uncle_Of',
                         'Sister_Of': 'Aunt_Of',
                         },
            'Aunt_Of': {'Son_Of': 'Cousin_Of',
                        'Daughter_Of': 'Cousin_Of',
                        'Brother_Of': 'Uncle_Of',
                        'Sister_Of': 'Aunt_Of',
                        }
        }
    return relation[previous][current]
