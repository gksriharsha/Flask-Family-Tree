from flask import Flask

from Tree.Utils.GremlinFunction import injectFunctions

app = Flask(__name__)

from gremlin_python.structure.graph import Graph
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.driver import client
from flask import request
from gremlin_python.process.traversal import T, Cardinality, TextP
from gremlin_python.process.graph_traversal import __

cli = client.Client('ws://localhost:8182/gremlin', 'g')
injectFunctions(cli)  # Functions responsible for loading relevant groovy scripts for application execution.
cli.close()

graph = Graph()
connection = DriverRemoteConnection('ws://localhost:8182/gremlin', 'g')
# The connection should be closed on shut down to close open connections with connection.close()
g = graph.traversal().withRemote(connection)
