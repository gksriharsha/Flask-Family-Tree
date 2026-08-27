"""WSGI entrypoint.

There was no module-level ``app`` anywhere, so ``gunicorn TreeServer:app`` could not start --
and CORS was registered inside ``if __name__ == '__main__'``, so no WSGI deployment emitted CORS
headers at all. Both are fixed by having a single factory that every entrypoint uses.

    gunicorn --bind 127.0.0.1:5000 --workers 2 wsgi:app
"""

from Tree import create_app

app = create_app()
