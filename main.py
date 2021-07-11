from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.structure.graph import Graph

graph = Graph()
connection = DriverRemoteConnection('ws://localhost:8182/gremlin', 'g')
# The connection should be closed on shut down to close open connections with connection.close()
g = graph.traversal().withRemote(connection)
# Reuse 'g' across the application

print(g)

herculesAge = g.V().has('name', 'hercules').values('age').next()
print('Hercules is {} years old.'.format(herculesAge))

hercules = g.V().has('name', 'hercules').next()
# val = g.V(16416).repeat(bothE().otherV().dedup()).until(has('name','Harsha')).path().by(__.elementMap()).by(__.elementMap()).next()

# list_offsprings = g.V().has('Name','Harsha').out('Brother_Of').elementMap().toList()
# print(list_offsprings)
# print(len(list_offsprings))
# print(list(vert.items()))
# print(v for (k,v) in list(vert.items()) if 'id' in k )
