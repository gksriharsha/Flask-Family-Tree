from flask import Flask
from flask import request

app = Flask(__name__)


from gremlin_python.structure.graph import Graph
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.process.graph_traversal import __
from gremlin_python.driver import client

graph = Graph()
connection = DriverRemoteConnection('ws://localhost:8182/gremlin', 'g')
# The connection should be closed on shut down to close open connections with connection.close()
g = graph.traversal().withRemote(connection)
