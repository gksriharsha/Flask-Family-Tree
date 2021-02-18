from datetime import datetime


def convert2dictionary(node):
    if isinstance(node, list) and len(node) > 1:
        resultList = []
        for i, j in enumerate(node):
            resultList.append(convertFromNode(j))

        return resultList
    else:
        return convertFromNode(node)


def convertFromNode(node):
    node_dictionary = {}
    for (k, v) in node.items():
        if type(k) == str:
            if isinstance(v, datetime):
                node_dictionary.update({k: v.strftime("%d/%m/%Y")})
            else:
                node_dictionary.update({k: v})

    return node_dictionary
