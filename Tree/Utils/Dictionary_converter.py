from datetime import date, datetime

from gremlin_python.process.traversal import T


def convert2dictionary(node):
    """Turn a Gremlin element map (or list of them) into plain dictionaries.

    An empty list now converts to an empty list rather than ``None``. Returning None for "no
    matches" made the client treat an empty search result as "not searching" and display the
    entire directory instead of an empty state.
    """
    if node is None:
        return None
    if isinstance(node, (list, tuple)):
        return [convertFromNode(item) for item in node]
    if node == {}:
        return None
    return convertFromNode(node)


def convertFromNode(node):
    """Convert one element map. Non-string keys (the T.id / T.label tokens) are dropped, and the
    vertex id is re-exposed as ``ID``."""
    node_dictionary = {}
    for key, value in node.items():
        if isinstance(key, str):
            if isinstance(value, (datetime, date)):
                node_dictionary[key] = value.isoformat()
            else:
                node_dictionary[key] = value

    if T.id in node:
        node_dictionary['ID'] = node[T.id]
    return node_dictionary
