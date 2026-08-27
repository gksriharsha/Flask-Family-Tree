class Occupation:
    def __init__(self, Organization='', Job='', Start_year=0, End_year=0):
        self.Organization = Organization
        self.Job = Job
        self.Start_year = Start_year
        self.End_year = End_year

    def __str__(self):
        return f'({self.Organization},{self.Job},{self.Start_year},{self.End_year})'

    @staticmethod
    def coerce(value):
        """Build an Occupation from whatever the client sent, or return None.

        The request mapper used to assign the raw JSON value straight onto ``person.Occupation``
        and the serialiser then read ``.Organization`` off it, so every request carrying an
        occupation raised AttributeError and returned a 500. A dict, a string and an existing
        Occupation are all accepted now.
        """
        if value is None or value == '':
            return None
        if isinstance(value, Occupation):
            return value
        if isinstance(value, dict):
            return Occupation(
                Organization=value.get('Organization', ''),
                Job=value.get('Job', ''),
                Start_year=value.get('Start_year', 0),
                End_year=value.get('End_year', 0),
            )
        # A bare string is treated as the job title.
        return Occupation(Job=str(value))
