import sys


def injectFunctions(cli):
    functions_file = open('functions.groovy', 'r')
    functions = functions_file.read()
    results = cli.submit(functions, request_options={'evaluationTimeout': 1000}).all().result()
    if results[0] is None:
        return
    else:
        print(results)
        print('Did not execute as intended')
        sys.exit(1)
