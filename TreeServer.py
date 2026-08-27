"""Development entrypoint.

Binds to the loopback interface by default. Every route in this application can read, rewrite or
delete family records, so exposing it on a routable interface is an explicit decision -- set
HOST if you mean it, and set FAMILYTREE_API_TOKEN first.

For anything other than local development use the WSGI entrypoint:

    gunicorn --bind 127.0.0.1:5000 --workers 2 wsgi:app
"""

import os

from Tree import create_app

if __name__ == '__main__':
    app = create_app()
    app.run(
        host=os.environ.get('HOST', '127.0.0.1'),
        port=int(os.environ.get('PORT', '5000')),
        debug=False,
    )
