class Occupation:
    def __init__(self, Organization: str = '', Job: str = '', Start_year: int = 0, End_year: int = 0):
        self.Organization: str = Organization
        self.Job: str = Job
        self.Start_year: int = Start_year
        self.End_year: int = End_year

    def __str__(self):
        return f'({self.Organization},{self.Job},{self.Start_year},{self.End_year})'
