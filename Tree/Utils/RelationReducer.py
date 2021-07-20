def reduce(relation_sequence):
    parse = relation_sequence
    print(parse)
    previous = None
    relation = []
    for i in range(1, len(parse)):
        if previous is None:
            previous = parse[0].replace('*', '')
        try:
            previous = relation_definition(previous, parse[i].replace('*', ''),
                                           relation_language='English')
        except KeyError as e:
            relation.append(previous)
            previous = parse[i]
    if relation is not None:
        relation.append(previous)
    else:
        relation = previous
    return relation


def relation_definition(previous, current, relation_language='Telugu'):
    if relation_language == 'Telugu':
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
            'Father_Of': {'Father_Of': 'Grandfather_Of', 'Brother_Of': 'Uncle_Of', 'Sister_Of': 'Aunt_Of',
                          'Mother_Of': 'GrandMother_Of'},
            'Husband_Of': {'Father_Of': 'Father in law_Of', 'Mother_Of': 'Mother in law_Of',
                           'Brother_Of': 'Brother in law_Of', 'Sister_Of': 'Sister in law_Of'},
            'Grandfather_Of': {'Brother_Of': 'Grandfather_Of', 'Son_Of': 'Uncle_Of'},
            'Uncle_Of': {'Son_Of', 'Cousin_Of'},
            'Son_Of': {'Son_Of': 'Grandson_Of', 'Wife_Of': 'Daughter in law_Of', 'Daughter_Of': 'Granddaughter_Of',
                       'Brother_Of': 'Son_Of'},
            'Daughter_Of': {'Husband_Of': 'Son in law_Of'},
            'Wife_Of': {'Father_Of': 'Father in law_Of', 'Mother_Of': 'Mother in law_Of',
                        'Brother_Of': 'Brother in law_Of', 'Sister_Of': 'Sister in law_Of'}
        }
    return relation[previous][current]


if __name__ == '__main__':
    pass
