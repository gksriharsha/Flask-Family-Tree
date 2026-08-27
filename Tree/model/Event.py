class Event:
    """A dated, optionally located occurrence -- birth, death, marriage.

    Fields are set in ``__init__`` rather than declared as class attributes. They used to be
    class-level annotations with no ``__init__``, so a fresh ``Event()`` had an empty instance
    ``__dict__`` -- and both serialisation sites use ``default=lambda o: o.__dict__``, which
    reads only the instance dict. The result was that the Birth and Death objects in API
    responses had a different shape for every record depending on which fields happened to be
    assigned.
    """

    def __init__(self, Date=None, Time=None, Location=None):
        self.Date = Date
        self.Time = Time
        self.Location = Location

    def is_empty(self):
        return self.Date is None and self.Time is None and self.Location is None

    def to_dict(self):
        return {'Date': self.Date, 'Time': self.Time, 'Location': self.Location}
