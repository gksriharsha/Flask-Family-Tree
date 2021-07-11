from Tree.Utils import CoordinateFetcher as cf
from Tree.Utils.CoordinateFetcher import InvalidCoordinateException


class Location:
    ID = None

    def __init__(self, place: str, state: str, country: str):
        self.place = place
        self.state = state
        self.country = country
        try:
            self.latitude, self.longitude = cf.getCoordinates(self.place, self.state)
        except InvalidCoordinateException:
            self.latitude = None
            self.longitude = None
