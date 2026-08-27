"""Coordinate lookup for a place.

The original scraped ``google.com/search`` HTML, selected a div by a CSS class that no longer
exists, and ran ``eval`` on the substrings it found -- so it evaluated remote HTML as Python. It
also had no timeout (an unbounded block inside a request), sent no User-Agent, interpolated the
place name into the URL unencoded, and dropped the country entirely even though the caller
collected and stored one.

This version calls a real geocoding API, parses JSON, and is disabled unless explicitly turned
on, so ``POST /add/location`` never depends on a third-party service to succeed.
"""

import logging

import requests

log = logging.getLogger(__name__)


class InvalidCoordinateException(Exception):
    """No usable coordinates were found for the place."""


def getCoordinates(place, state=None, country=None, *, url, user_agent, timeout):
    query = ', '.join(part for part in (place, state, country) if part)
    if not query:
        raise InvalidCoordinateException('No place supplied.')

    try:
        response = requests.get(
            url,
            params={'q': query, 'format': 'json', 'limit': 1},
            headers={'User-Agent': user_agent, 'Accept': 'application/json'},
            timeout=timeout,
        )
        response.raise_for_status()
        results = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise InvalidCoordinateException(f'Lookup failed for {query!r}: {exc}') from exc

    if not results:
        raise InvalidCoordinateException(f'No match for {query!r}.')

    try:
        latitude = float(results[0]['lat'])
        longitude = float(results[0]['lon'])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise InvalidCoordinateException(f'Unexpected response shape for {query!r}.') from exc

    log.info('Geocoded %r to (%s, %s)', query, latitude, longitude)
    return latitude, longitude
