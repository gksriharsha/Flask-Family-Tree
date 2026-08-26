/* groovylint-disable CompileStatic, ExplicitCallToMinusMethod, SimpleDateFormatMissingLocale, VariableTypeRequired */
/* groovylint-disable-next-line LineLength */
/* groovylint-disable DuplicateStringLiteral, MethodParameterTypeRequired,MethodReturnTypeRequired, NestedForLoop, NoDef */

/* ============================================================================
 * Server-side helper functions.
 *
 * WHAT WAS FIXED IN THIS PASS: every local is now declared with `def`. Groovy treats an
 * assignment to an undeclared name as a write to the script Binding, and Gremlin Server keeps
 * ONE script engine for all sessionless requests -- so these were entries in a single
 * process-wide map shared by every concurrent request on every gremlinPool thread. Two
 * simultaneous calls could read each other's `gender1`, `path` or `siblings`, which is a silent
 * graph-corruption path under any concurrent use.
 *
 * WHAT IS STILL KNOWN-BROKEN, deliberately left for the next pass so this diff stays reviewable:
 *
 *   1. `T.ID` does not exist in TinkerPop -- the token is `T.id`, and for an element id the step
 *      is `.id()` rather than `values(...)`. It appears 16 times below. Note that the ordinary
 *      path through relation() does NOT touch any of them and works (verified against a live
 *      graph: it returns a correct 'Cousin_Of'); the T.ID sites sit in the adoption and
 *      consanguinity branches.
 *   1b. marriage() fails before reaching any T.ID site, with "the traversal can no longer be
 *      modulated": it calls cousinMarraige.hasNext(), which executes the traversal, and then
 *      appends .path() to the already-executed traversal. The fix is the .clone() idiom this
 *      file already uses elsewhere. Verified live: POST /relate/people with Relation=Marriage
 *      returns 500.
 *   2. adoption() reads `lastname` one line before it is assigned -- a deterministic throw on
 *      every call, which also makes siblings() unreachable.
 *   3. child() never calls siblings(), so biological siblings get no sibling edges. (The
 *      duplicate-parent1 half of this defect IS fixed: the child's upward edge now goes to
 *      each parent once.)
 *   4. child() names its own parameter `adoption`, shadowing the function it tries to call, so
 *      the same-sex-parents branch resolves to Boolean.call().
 *   5. siblings() calls `g(parent2)` without `.V()`, calls siblings_relation with 2 arguments
 *      against a 3-parameter definition, and misspells 'Mother_of'.
 *   6. divorce() writes self-loops (`.to(V(person1))` from person1) and is unreferenced.
 *   7. No repeat() traversal has a times()/limit() cutoff.
 *
 * DEPLOYMENT NOTE: these definitions should be loaded by Gremlin Server itself through
 * ScriptFileGremlinPlugin (see docker-compose.yml), not submitted by the application at
 * startup. Submitting them through a sessionless client only works as a side effect of the
 * engine's global-closure cache: the definitions are lost on every Gremlin Server restart and
 * exist on only one node behind a load balancer.
 * ========================================================================= */
def relation(g, from, to) {
    // Locals declared so assignment targets the method frame. Without `def` these
    // are entries in one process-wide Binding shared by every concurrent request.
    def adoptedCheck = null
    def adoptedID = null
    def count = null
    def multiplePath = null
    def multipleRelation = null
    def parentID = null
    def path = null
    def people = null
    def relationshipID = null
    def secondPath = null
    def significantOther = null
    def temp = null

    adoptedCheck  = g.V().has(id, from).repeat(out().dedup()).until(has(id, to)).path()\
    .unfold().where(has('Adopted', 'Yes'))

    if (adoptedCheck.clone().hasNext()) {
        parentID = adoptedCheck.clone().in('Father_Of*').values(T.ID).next()
        // If an adopted child is found in the shortest path.
        adoptedID = g.V(parentID).out('Father_Of*').values(T.ID).next()
       
        /* If the shortest path between the final person and the first person has an
        option of adoption then it will be included as a secondary relation*/
        path = g.V(from).repeat(inE().otherV().dedup()).until(has(id, to)).path()\
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
            temp = g.V(from).repeat(inE().otherV().dedup()).until(has(id,parentID)).path().by('Firstname').by(label)\
            .next().collect()
            temp.removeLast()
            secondPath = temp + \
            g.V(parentID).repeat(inE().otherV().dedup()).until(has(id, to)).path().by('Firstname').by(label).next()
            path << secondPath
        }
        path[0] = path[0].collect()
    }
    else {
        path = g.V().has(id, from).repeat(inE().otherV().dedup()).until(has(id, to)).path()\
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
                multiplePath = g.V(from).repeat(inE().not(has(id, relationshipID)).otherV().dedup())\
                .until(has(id, to)).path().by('Firstname').by(label).next()
                people = people.minus([person, significantOther])
            }
            else {
                multiplePath = g.V(from).repeat(inE().otherV().not(has(id,significantOther)).dedup())\
                                .until(has(id, person)).path()\
                                .by('Firstname').by(label).next().collect()
                multiplePath.removeLast()
                multiplePath = multiplePath + g.V(person).inE('Husband_Of', 'Wife_Of')\
                                .repeat(inE().otherV().dedup()).until(has(id, to)).path().by('Firstname').by(label)\
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
def shortestPath(g,from,to){
    // Locals declared so assignment targets the method frame. Without `def` these
    // are entries in one process-wide Binding shared by every concurrent request.
    def path = null
    path = g.V().has(id, from).repeat(inE().otherV().dedup()).until(has(id, to)).path()\
        .by('Firstname').by(label).next()
    return path 
}
def adoption(g, parent1, parent2, child, Map kwargs =[:]) {
    // Locals declared so assignment targets the method frame. Without `def` these
    // are entries in one process-wide Binding shared by every concurrent request.
    def gender = null
    def lastname = null
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
        if(kwargs.Father_lastname){
            if(g.V(parent1).values('Gender').next() == 'Male'){
                g.V(child).property('Lastname',g.V(parent1).values('Lastname').next()).next()
            }
            else{
                g.V(child).property('Lastname',g.V(parent2).values('Lastname').next()).next()
            }
            
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
    siblings(g,parent1,parent2,child)
}
def siblings_relation(g,sibling,siblings) {
    // Locals declared so assignment targets the method frame. Without `def` these
    // are entries in one process-wide Binding shared by every concurrent request.
    def addition = null
    def gender = null
    addition = ''
    if (g.V(sibling).values('Adopted').next() == 'Yes') {
        addition = '*'
    }
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
def siblings(g, parent1, parent2,child) {
    // Locals declared so assignment targets the method frame. Without `def` these
    // are entries in one process-wide Binding shared by every concurrent request.
    def siblings = null
    def siblings1 = null
    def siblings2 = null

    // parent1 is usually the father and parent 2 is usually the mother.
    
    if (parent1 && parent2) { // Both parents exist

        if ((g.V(parent1).out('Husband_Of').values(T.ID).next() == parent2) ||
        g.V(parent2).out('Husband_Of').values(T.ID).next() == parent1) {   // Both parents are married.
        
            siblings = g(parent2).out('Mother_Of*','Father_Of*').values(T.ID).fold().next()
            siblings.addAll(g(parent2).out('Mother_Of','Father_Of').values(T.ID).fold().next())
            siblings_relation(g,child,siblings)
            return
    }
        siblings1 = g.V(parent2).out('Mother_Of','Father_Of').values(T.ID).fold().next()
        siblings2 = g.V(parent1).out('Father_Of','Mother_Of').values(T.ID).fold().next()
        siblings = siblings1.intersect(siblings2)
        siblings_relation(child,siblings)
        return
    }
    else if (parent1 || parent2) { //Only father or mother adopted a child.
        if(parent1)
        {
            siblings = g.V(parent1).out('Father_Of','Mother_of').values(T.ID).fold().next()
        }
        else
        {
            siblings = g.V(parent2).out('Father_Of','Mother_of').values(T.ID).fold().next()
        }
        siblings_relation(child,siblings)
        return 
    }
    else{
        // Throw an error because both mother and father do not exist.
    }
}
def marriage(g, person1, person2) {
    // Locals declared so assignment targets the method frame. Without `def` these
    // are entries in one process-wide Binding shared by every concurrent request.
    def cousinMarraige = null
    def gender1 = null
    def gender2 = null
    def i = null
    def marriageID = null
    def path = null
    def person3 = null
    def person4 = null
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

    cousinMarraige = g.V(person1).repeat(inE('Father_Of', 'Son_Of', 'Mother_Of', 'Daughter_Of',
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
        g.E(g.V(person2).outE('Husband_Of','Wife_Of').id().next()).drop().next()

        g.V(person1).addE('ex-spouse_Of').to(V(person1)).next()
        g.V(person2).addE('ex-spouse_Of').to(V(person2)).next()
    }
}

def ageDifference(g, person1, person2) {
    // Locals declared so assignment targets the method frame. Without `def` these
    // are entries in one process-wide Binding shared by every concurrent request.
    def DOB1 = null
    def DOB2 = null
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
                    // Was `.to(V(parent1))` twice, so the mother never received the child's
                    // upward edge and the father received two. Confirmed against a live graph:
                    // father in=[Son_Of, Son_Of], mother in=[].
                    g.V(child).addE('Son_Of').to(V(parent2)).next()
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
                    // Same defect as the Son_Of branch above.
                    g.V(child).addE('Daughter_Of').to(V(parent2)).next()
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

