from datetime import datetime
from gremlin_python.process.traversal import T


def convert2dictionary(node):
    """
    This function takes in element map or value map of a gremlin node and outputs the node properties as a dictionary

    Parameters
    ----------
    node

    Returns
    -------

    """
    if node == [] or node == {}:
        return None
    if isinstance(node, list) and len(node) > 0:
        resultList = []
        for i, j in enumerate(node):
            resultList.append(convertFromNode(j))

        return resultList
    else:
        return convertFromNode(node)


def convertFromNode(node):
    """
    This is a helper function to the above function. This function only processes, one node's information at a time.
    Therefore, the task of dividing the list of nodes is done by the previous funciton.
    Parameters
    ----------
    node

    Returns
    -------

    """
    node_dictionary = {}
    for (k, v) in node.items():
        if type(k) == str:
            if isinstance(v, datetime):
                node_dictionary.update({k: v.strftime("%d/%m/%Y")})
            else:
                node_dictionary.update({k: v})

    node_dictionary.update({'ID': node[T.id]})

    return node_dictionary
