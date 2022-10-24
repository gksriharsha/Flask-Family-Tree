# Flask-Family-Tree

The goal of this repository is to build an API for tree traversal in famliy tree. The UI for this project is on [github](https://github.com/gksriharsha/Family-Tree-UI). These projects together run the family tree software.

The demonstration of the family tree software can be seen in the following [gif](https://j.gifs.com/WP0Q5J.gif).

## Demo

[![Demo Flask-Family-Tree alpha](https://j.gifs.com/WP0Q5J.gif)](https://j.gifs.com/WP0Q5J.gif)

This project uses JanusGraph software with Cassandra as Storage Backend and ElasticSearch as Index Backend. Along with the JanusGraph software, I have used `gremlinpython` python package to establish a connection to the Gremlin Server to execute the gremlin query. 

The subpackages of this project which interact with the gremlin server are present in the `gremlinInterface.py`. These files contain the helper functions designed to achieve the functionality of the project.

More about this project can be understood from [my Medium account](https://gksriharsha.medium.com/). The most important article addressing the gremlin traversal is [this one](https://gksriharsha.medium.com/gremlin-traversals-dont-get-lost-in-the-route-5-8d277cf70899).
