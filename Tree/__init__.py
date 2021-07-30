from flask import Flask
import os
import glob

fileList = glob.glob(os.path.abspath('Tree/faces/unknown/*.*'))
for file in fileList:
    os.remove(file)


from gremlin_python.process.traversal import T, Cardinality, TextP
from gremlin_python.process.graph_traversal import __

from Tree.Utils.GremlinFunction import injectFunctions
from gremlin_python.structure.graph import Graph
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.driver import client
from Tree.config import Configuration as General_Configuration

graph = Graph()
connection = DriverRemoteConnection('ws://localhost:8182/gremlin', 'g')
# The connection should be closed on shut down to close open connections with connection.close()
g = graph.traversal().withRemote(connection)

from Tree.people.routes import people
from Tree.relations.routes import relations
from Tree.location.routes import locations
from Tree.base.routes import base
from Tree.faces.routes import faces



def create_app(configuration=General_Configuration):
    app = Flask(__name__)
    app.config.from_object(configuration)

    app.register_blueprint(people)
    app.register_blueprint(relations)
    app.register_blueprint(locations)
    app.register_blueprint(base)
    app.register_blueprint(faces)

    cli = client.Client('ws://localhost:8182/gremlin', 'g')
    injectFunctions(cli)  # Functions responsible for loading relevant groovy scripts for application execution.
    cli.close()

    return app