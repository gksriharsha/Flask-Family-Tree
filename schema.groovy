/* JanusGraph schema declaration. Idempotent: safe to run repeatedly.
 *
 * WHY THIS FILE EXISTS. Nothing in the original project ever declared a schema -- no
 * makePropertyKey, no makeVertexLabel, no buildIndex anywhere. JanusGraph therefore auto-created
 * every property key from whatever the first write happened to imply, with two consequences that
 * both showed up the moment the application was run against a real server:
 *
 *   1. Cardinality conflicts. The demo seed writes dates with a plain property() call, which
 *      creates the key as SINGLE. The API then writes the same key with SET cardinality (the
 *      multi-calendar intent from Notes.md) and the server rejects it:
 *      "Key is defined for SINGLE cardinality which conflicts with specified: set".
 *      Declaring the cardinality once, up front, is the only way both paths can agree.
 *
 *   2. Full scans. With no index, every g.V().has('Firstname', ...) walks the whole graph, and
 *      TextP.containing has no index to use at all -- which is why the project provisioned an
 *      index backend it never actually benefited from.
 *
 * ORDER MATTERS: apply this to an empty graph, before seeding. Creating an index over a key that
 * already holds data leaves the index INSTALLED rather than ENABLED and requires a reindex job.
 */

def mgmt = graph.openManagement()
def created = []
def conflicts = []

// --- property keys -------------------------------------------------------------------------
def SINGLE = org.janusgraph.core.Cardinality.SINGLE
def SET = org.janusgraph.core.Cardinality.SET

def key = { String name, Class type, cardinality ->
    def existing = mgmt.getPropertyKey(name)
    if (existing == null) {
        created << ('key:' + name)
        return mgmt.makePropertyKey(name).dataType(type).cardinality(cardinality).make()
    }
    if (existing.cardinality() != cardinality) {
        // Cardinality cannot be altered on an existing key, so this is reported rather than
        // patched. On a development graph, reset and re-apply; on a real one, migrate the key.
        conflicts << (name + ' is ' + existing.cardinality().toString() + ', expected ' + cardinality.toString())
    }
    return existing
}

// Person: identity and status.
['Firstname', 'Lastname', 'Gender', 'Alive', 'Nickname'].each { key(it, String.class, SINGLE) }

// Person: flags the Groovy helpers set.
['Adopted', 'Homosexual', 'Married to Relative'].each { key(it, String.class, SINGLE) }

// Person: birth and death. Dates and occupation are SET so one person can hold the same fact in
// several calendars, which is the deliberate decision recorded in Notes.md.
['Date_of_birth', 'Date_of_death', 'Occupation'].each { key(it, String.class, SET) }
['Place_of_birth', 'Place_of_death', 'Time_of_birth', 'Time_of_death'].each {
    key(it, String.class, SINGLE)
}

// Location.
['Place', 'State', 'Country'].each { key(it, String.class, SINGLE) }

// KinshipTerm: the family's own words.
['Base_term', 'Term', 'Roman', 'Usage', 'Vocabulary_side'].each { key(it, String.class, SINGLE) }

// TreeSettings: where this tree's files live. The folder is the durable copy of the tree —
// the graph is a working index that can be rebuilt from it.
['Gedcom_path', 'Created'].each { key(it, String.class, SINGLE) }
['Latitude', 'Longitude'].each { key(it, Double.class, SINGLE) }

// --- vertex labels -------------------------------------------------------------------------
// KinshipTerm holds the words a family uses for a relationship. The relationship itself is
// never stored: it is computed from the parent and union links every time it is shown, so a
// word can be changed, or a whole regional vocabulary swapped, without touching the data.
['Person', 'Location', 'KinshipTerm', 'TreeSettings'].each {
    if (mgmt.getVertexLabel(it) == null) { created << ('vertex:' + it); mgmt.makeVertexLabel(it).make() }
}

// --- edge labels ---------------------------------------------------------------------------
// The '*' suffixed variants mark adoptive links. MULTI because a pair can legitimately be
// connected by the same label more than once over time.
def edgeLabels = ['Father_Of', 'Mother_Of', 'Son_Of', 'Daughter_Of',
                  'Husband_Of', 'Wife_Of', 'Brother_Of', 'Sister_Of',
                  'Father_Of*', 'Mother_Of*', 'Son_Of*', 'Daughter_Of*',
                  'Brother_Of*', 'Sister_Of*',
                  // Sex-neutral equivalents. The gendered labels above cannot express a
                  // parent, child or spouse whose sex is unrecorded or is neither male nor
                  // female, so without these the interface would have to demand a sex before
                  // it would accept a link — turning an honest "not known" into a forced
                  // guess. Readers treat these exactly like their gendered counterparts.
                  'Parent_Of', 'Parent_Of*', 'Child_Of', 'Child_Of*', 'Partner_Of',
                  'ex-spouse_Of', 'BORN_IN', 'NATIVE_TO',
                  // A birth order somebody remembers. Stored as a fact of its own rather
                  // than as a guessed date, because a guessed date is an invented record —
                  // and Telugu cannot name a brother or a paternal uncle without this.
                  'ELDER_THAN',
                  // Person -> KinshipTerm: the word always used for this one individual.
                  'PINNED_TERM']
edgeLabels.each {
    if (mgmt.getEdgeLabel(it) == null) {
        created << ('edge:' + it)
        mgmt.makeEdgeLabel(it).multiplicity(org.janusgraph.core.Multiplicity.MULTI).make()
    }
}

// --- indexes -------------------------------------------------------------------------------
def vertexClass = org.apache.tinkerpop.gremlin.structure.Vertex.class

// Composite indexes: exact-match lookups. Without these, every has('Firstname', x) is a scan.
if (mgmt.getGraphIndex('personByFirstname') == null) {
    created << 'index:personByFirstname'
    mgmt.buildIndex('personByFirstname', vertexClass)
        .addKey(mgmt.getPropertyKey('Firstname'))
        .indexOnly(mgmt.getVertexLabel('Person'))
        .buildCompositeIndex()
}
if (mgmt.getGraphIndex('personByLastname') == null) {
    created << 'index:personByLastname'
    mgmt.buildIndex('personByLastname', vertexClass)
        .addKey(mgmt.getPropertyKey('Lastname'))
        .indexOnly(mgmt.getVertexLabel('Person'))
        .buildCompositeIndex()
}
if (mgmt.getGraphIndex('locationByPlace') == null) {
    created << 'index:locationByPlace'
    mgmt.buildIndex('locationByPlace', vertexClass)
        .addKey(mgmt.getPropertyKey('Place'))
        .indexOnly(mgmt.getVertexLabel('Location'))
        .buildCompositeIndex()
}

// Mixed index: this is what makes the substring name search (TextP.containing) indexed rather
// than a full graph walk. TEXTSTRING supports both full-text and exact string predicates.
if (mgmt.getGraphIndex('termByBase') == null) {
    created << 'index:termByBase'
    mgmt.buildIndex('termByBase', vertexClass)
        .addKey(mgmt.getPropertyKey('Base_term'))
        .indexOnly(mgmt.getVertexLabel('KinshipTerm'))
        .buildCompositeIndex()
}

if (mgmt.getGraphIndex('personSearch') == null) {
    created << 'index:personSearch'
    def textstring = org.janusgraph.core.schema.Mapping.TEXTSTRING.asParameter()
    mgmt.buildIndex('personSearch', vertexClass)
        .addKey(mgmt.getPropertyKey('Firstname'), textstring)
        .addKey(mgmt.getPropertyKey('Lastname'), textstring)
        .buildMixedIndex('search')
}

mgmt.commit()

return ['created': created, 'conflicts': conflicts]
