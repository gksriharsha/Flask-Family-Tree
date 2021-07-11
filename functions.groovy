/* groovylint-disable CompileStatic, ExplicitCallToMinusMethod, SimpleDateFormatMissingLocale, VariableTypeRequired */
/* groovylint-disable-next-line LineLength */
/* groovylint-disable DuplicateStringLiteral, MethodParameterTypeRequired,MethodReturnTypeRequired, NestedForLoop, NoDef */
def relation(g, from, to) {

    adoptedCheck  = g.V().has(id, from).repeat(out().dedup()).until(has(id, to)).path()\
    .unfold().where(has('Adopted', 'Yes'))

    if (adoptedCheck.clone().hasNext()) {
        parentID = adoptedCheck.clone().in('Father_Of*').values(T.ID).next()
        // If an adopted child is found in the shortest path.
        adoptedID = g.V(parentID).out('Father_Of*').values(T.ID).next()
       
        /* If the shortest path between the final person and the first person has an
        option of adoption then it will be included as a secondary relation*/
        path = g.V(from).repeat(outE().otherV().dedup()).until(has(id, to)).path()\
        .by('Firstname').by(label).fold().next()

        temp = g.V(from).repeat(out().dedup()).until(has(id,parentID)).path().by(T.ID).next().collect()
        temp.removeLast()
        secondPath = temp + \
        g.V(parentID).repeat(out().dedup()).until(has(id, to)).path().by(T.ID).next().collect()
        count = 0
        
        for(item in secondPath){
            if(item == adoptedID){
                count = count + 1
            }
        }
        
        if (count <= 1)
        {
            temp = g.V(from).repeat(outE().otherV().dedup()).until(has(id,parentID)).path().by('Firstname').by(label)\
            .next().collect()
            temp.removeLast()
            secondPath = temp + \
            g.V(parentID).repeat(outE().otherV().dedup()).until(has(id, to)).path().by('Firstname').by(label).next()
            path << secondPath
        }
        path[0] = path[0].collect()
    }
    else {
        path = g.V().has(id, from).repeat(outE().otherV().dedup()).until(has(id, to)).path()\
        .by('Firstname').by(label).next()
    }

    multipleRelation = g.V().has(id, from).repeat(out().dedup()).until(has(id, to)).path()\
    .unfold().where(has('Married to Relative', 'Yes'))
    if (multipleRelation.clone().hasNext()) {
        people = multipleRelation.clone().values(T.ID).fold()
        def person = people[0]
        while (true) {
            if (people == []) {
                break
            }
            person = people[0]
            significantOther = g.V(person).out('Husband_Of', 'Wife_Of').values(T.ID).next()
            relationshipID = g.V(person).outE('Husband_Of', 'Wife_Of').id().next()
            if (people.contains(significantOther)) {
                multiplePath = g.V(from).repeat(outE().not(has(id, relationshipID)).otherV().dedup())\
                .until(has(id, to)).path().by('Firstname').by(label).next()
                people = people.minus([person, significantOther])
            }
            else {
                multiplePath = g.V(from).repeat(outE().otherV().not(has(id,significantOther)).dedup())\
                                .until(has(id, person)).path()\
                                .by('Firstname').by(label).next().collect()
                multiplePath.removeLast()
                multiplePath = multiplePath + g.V(person).outE('Husband_Of', 'Wife_Of')\
                                .repeat(outE().otherV().dedup()).until(has(id, to)).path().by('Firstname').by(label)\
                                .next()
                people = people.minus([person])
            }
            path << multiplePath
            multiplePath = ''
        }
    }
    // TODO: Add logic to find out mixed cases.
    // If there is a adoption in a path which has marriage in the inner circle or viceversa.
    return path
}
def adoption(g, parent1, parent2, child, Map kwargs =[:]) {
    gender = g.V(child).values('Gender').next()
    g.V(child).property('Adopted', 'Yes').next()

    if (parent1) {
        g.V(child).property('Lastname', lastname).next()
        lastname = g.V(parent1).values('Lastname').next()
        g.V(parent1).addE('Father_Of*').to(V(child)).next()
        if (gender == 'Male') {
            g.V(child).addE('Son_Of*').to(V(parent1)).next()
        }
        else {
            g.V(child).addE('Daughter_Of*').to(V(parent1)).next()
        }
    }
    else {
        if (kwargs.Lastname) {
            g.V(child).property('Lastname', kwargs.Lastname).next()
        }
    }
    if (parent2) {
        g.V(parent2).addE('Mother_Of*').to(V(child)).next()
        if (gender == 'Male') {
            g.V(child).addE('Son_Of*').to(V(parent2)).next()
        }
        else {
            g.V(child).addE('Daughter_Of*').to(V(parent2)).next()
        }
    }
    siblings(adopted = true)
}
def siblings_relation(siblings, adopted) {
    addition = ''
    if (adopted) {
        addition = '*'
    }
    for (sibling in siblings) {
        gender = g.V(sibling).values('Gender').next()
        if (gender == 'Male') {
            for (s in siblings) {
                if (s != sibling) {
                    g.V(sibling).addE('Brother_Of' + addition).to(V(s)).next()
                }
            }
        }
        else {
            for (s in siblings) {
                if (s != sibling) {
                    g.V(sibling).addE('Sister_Of' + addition).to(V(s)).next()
                }
            }
        }
    }
}
def siblings(g, father, mother, adopted=false) {
    if (father && mother && g.V(father).out('Husband_Of').values(T.ID).next() == mother) {
        if (adopted) {
            siblings = g(mother).out('Mother_Of*').values(T.ID).fold().next()
            siblings_relation(siblings, true)
            return
        }
        siblings = g(mother).out('Mother_Of').values(T.ID).fold().next()
        siblings_relation(siblings, false)
        return
    }
    if (father && mother) { // Father and mother exist but are not married.
        addition = ''
        if (adopted) {
            addition = '*'
        }
        siblings1 = g.V(mother).out('Mother_Of' + addition).values(T.ID).fold().next()
        siblings2 = g.V(father).out('Father_Of' + addition).values(T.ID).fold().next()
        siblings = siblings1.intersect(siblings2)
        siblings_relation(siblings, adopted)
        return
    }
    if (father) { //Only father and adopted a child.
        addition = ''
        if (adopted) {
            addition = '*'
        }
        siblings2 = g.V(father).out('Father_Of' + addition).values(T.ID).fold().next()
        siblings_relation(siblings, adopted)
        return
    }
    if (mother) { // Only mother and adopted a child
        addition = ''
        if (adopted) {
            addition = '*'
        }
        siblings2 = g.V(mother).out('Mother_Of' + addition).values(T.ID).fold().next()
        siblings_relation(siblings, adopted)
        return
    }
}
def marriage(g, person1, person2) {
    gender1 = g.V(person1).values('Gender').next()
    gender2 = g.V(person2).values('Gender').next()

    if (gender1 == gender2) {
        g.V(person1).property('Homosexual', 'Yes').next()
        g.V(person2).property('Homosexual', 'Yes').next()
    }

    if (gender1 == 'Male') {
        g.V(person1).addE('Husband_Of').to(V(person2)).next()
    }
    else {
        g.V(person1).addE('Wife_Of').to(V(person2)).next()
    }

    if (gender2 == 'Male') {
        g.V(person2).addE('Husband_Of').to(V(person1)).next()
    }
    else {
        g.V(person2).addE('Wife_Of').to(V(person1)).next()
    }
    marriageID = g.V(person1).outE('Husband_Of', 'Wife_Of').id().next()

    cousinMarraige = g.V(person1).repeat(outE('Father_Of', 'Son_Of', 'Mother_Of', 'Daughter_Of',
                                                    'Wife_Of','Husband_Of','Son_Of*','Daughter_Of*',
                                                    'Father_Of*', 'Mother_Of*').not(has(id, marriageID)).otherV()\
                                                    .dedup()).until(has(id, person2))
    i = 0
    if (cousinMarraige.hasNext()) {
        path = cousinMarraige.path().by(T.ID).by(label).next()
        for (item in path) {
            if (item == 'Husband_Of' || item == 'Wife_Of') {
                person3 = path[i - 1]
                person4 = path[i + 1]
                break
            }
            i = i + 1
        }
        if (ageDifference(g.V(person1).values('Date_of_birth').next(),
                          g.V(person3).values('Date_of_birth').next()) > 0) {
            // Person1 is elder to Person3
            g.V(person3).property('Married to Relative', 'Yes').next()
            g.V(person4).property('Married to Relative', 'Yes').next()
                          }
        else {
            g.V(person1).property('Married to Relative', 'Yes').next()
            g.V(person2).property('Married to Relative', 'Yes').next()
        }
    }
}
def divorce(g,person1,person2){
    if(g.V(person1).out('Husband_Of','Wife_Of').values(T.ID).next() == person2){
        g.E(g.V(person1).outE('Husband_Of','Wife_Of').id().next()).drop().next()
    }
    g.V(person1).addE('ex-spouse_Of').to(V(person1)).next()
    g.V(person2).addE('ex-spouse_Of').to(V(person2)).next()
}

// class AgeException extends Exception {
//     String s1;
//     AgeException(String s2) {
//         s1 = s2
//     }
//     @Override
//     String toString() {
//         return('The exception is ' + s1)
//     }

// }
def ageDifference(g, person1, person2) {
    DOB1 = g.V(person1).values('Date_of_birth').next()
    DOB2 = g.V(person2).values('Date_of_birth').next()
    def sdf = new java.text.SimpleDateFormat('yyyy-MM-dd')
    sdf.lenient = false
    def val1 = sdf.parse(DOB1)
    def val2 = sdf.parse(DOB2)
    long diff = val2.getTime() - val1.getTime()
    return diff / (1000l * 60 * 60 * 24 * 365)
}
def child(g, parent1, parent2, child, adoption=false) {
    if (g.V(parent1).values('Gender').next() == g.V(parent2).values('Gender').next()) {
        adoption(g, parent1, parent2, child)
    }
    else {
        if (g.V(child).values('Gender').next() == 'Male') {
            if (adoption) {
                g.V(child).addE('Son_Of*').to(V(parent1)).next()
                g.V(child).addE('Son_Of*').to(V(parent2)).next()
            }
            else {
                if (ageDifference(g, parent1, child) > 13 && \
                     ageDifference(g, parent2, child) > 13) {
                    g.V(child).addE('Son_Of').to(V(parent1)).next()
                    g.V(child).addE('Son_Of').to(V(parent1)).next()
                     }
            }
        }
        else {
            if (adoption) {
                g.V(child).addE('Daughter_Of*').to(V(parent1)).next()
                g.V(child).addE('Daughter_Of*').to(V(parent2)).next()
            }
            else {
                if (ageDifference(g, parent1, child) > 13 && \
                     ageDifference(g, parent2, child) > 13) {

                 //TODO: Add exceptions when illogical steps are found

                    g.V(child).addE('Daughter_Of').to(V(parent1)).next()
                    g.V(child).addE('Daughter_Of').to(V(parent1)).next()
                }
            }
        }
        if (ageDifference(g, parent1, child) > 13 && \
                     ageDifference(g, parent2, child) > 13) {
            if (g.V(parent1).values('Gender').next() == 'Male') {
                g.V(parent1).addE('Father_Of').to(V(child)).next()
                g.V(parent2).addE('Mother_Of').to(V(child)).next()
            }
            else {
                g.V(parent1).addE('Mother_Of').to(V(child)).next()
                g.V(parent2).addE('Father_Of').to(V(child)).next()
            }
        }
    }
}

//TODO: Test cases to test multiple relations between people .

