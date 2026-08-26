import logging

from Tree.Utils.CoordinateFetcher import InvalidCoordinateException, getCoordinates

log = logging.getLogger(__name__)


class Location:
    """A place.

    Coordinate lookup used to happen in ``__init__`` with no way to switch it off, and passed
    ``state`` straight into ``str.replace`` -- so a request without a State raised
    ``AttributeError: 'NoneType' object has no attribute 'replace'``, which the caller's
    ``InvalidCoordinateException`` handler did not catch.
    """

    def __init__(self, place, state=None, country=None, geocoder=None):
        self.ID = None
        self.place = place
        self.state = state
        self.country = country
        self.latitude = None
        self.longitude = None

        if geocoder is not None:
            try:
                self.latitude, self.longitude = geocoder(place, state, country)
            except InvalidCoordinateException as exc:
                log.info('No coordinates for %r: %s', place, exc)

    @staticmethod
    def geocoder_from_config(config):
        """Return a callable that geocodes, or None when geocoding is disabled."""
        if not config.get('GEOCODING_ENABLED'):
            return None

        def _geocode(place, state, country):
            return getCoordinates(
                place, state, country,
                url=config['GEOCODING_URL'],
                user_agent=config['GEOCODING_USER_AGENT'],
                timeout=config['GEOCODING_TIMEOUT_S'],
            )

        return _geocode
