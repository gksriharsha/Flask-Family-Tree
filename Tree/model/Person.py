from Tree.model.Event import Event


class Person:
    """
        This class is used for performing person based operations
    """

    def __init__(self, Firstname: str = None, Gender=None, Lastname=None, Alive=False) -> object:
        """

        Parameters
        ----------
        Firstname : str
        Date is stored as a string in dd/mm/yyyy format.
        Gender : str
        Gender is stored as a string
        Lastname : str
        Alive: bool

        Returns
        -------
        None
        """
        self.Firstname = Firstname
        self.Lastname = Lastname
        self.Gender = Gender
        self.Alive = Alive

        self.Birth = None
        self.Death = None
        self.Occupation = None
        self.native_to = None

    @property
    def birth(self):
        return self.Birth

    @birth.setter
    def birth(self, value):
        if isinstance(value,Event):
            self.Birth = value

    @property
    def death(self):
        return self.Death

    @death.setter
    def death(self, value):
        if isinstance(value, Event):
            self.Death = value

    def convert_to_gremlin_node(self):
        gremlinDictionary = {}
        gremlinDictionary.update({'Gender': self.Gender})
        gremlinDictionary.update({'Alive': self.Alive})
        gremlinDictionary.update({'Firstname': self.Firstname})
        gremlinDictionary.update({'Lastname': self.Lastname})
        if self.Occupation:
            gremlinDictionary.update({'Occupation': self.Occupation})
        if self.Birth is not None:
            if self.Birth.Location is not None:
                gremlinDictionary.update({'Place_of_birth': self.Birth.Location['ID']})
            if self.Birth.Date is not None:
                gremlinDictionary.update({'Date_of_birth': self.Birth.Date})
            if self.Birth.Time is not None:
                gremlinDictionary.update({'Time_of_birth': self.Birth.Time})
        if self.Death is not None:
            if self.Death.Location is not None:
                gremlinDictionary.update({'Place_of_death':self.Death.Location['ID']})
            if self.Death.Date is not None:
                gremlinDictionary.update({'Date_of_death':self.Death.Date})
            if self.Death.Time is not None:
                gremlinDictionary.update({'Time_of_death':self.Death.Time})
        return gremlinDictionary

    @staticmethod
    def createPersonObject(attributes):
        p = Person()
        if 'Gender' in attributes.keys():
            p.Gender = attributes.pop('Gender')
        if 'Alive' in attributes.keys():
            p.Alive = attributes.pop('Alive')
        if 'Firstname' in attributes.keys():
            p.Firstname = attributes.pop('Firstname')
        if 'Lastname' in attributes.keys():
            p.Lastname = attributes.pop('Lastname')
        if 'Occupation' in attributes.keys():
            p.Occupation = attributes.pop('Occupation')
        if any('birth' in str(x) for x in  attributes.keys()):
            e = Event()
            try:
                e.Date = attributes.pop('Date_of_birth')
            except:
                pass
            try:
                e.Time = attributes.pop('Time_of_birth')
            except:
                pass
            try:
                e.Location = attributes.pop('Place_of_birth')
            except:
                pass
            p.birth = e
        if 'death' in attributes.keys():
            e = Event()
            try:
                e.Date = attributes.pop('Date_of_death')
            except:
                pass
            try:
                e.Time = attributes.pop('Time_of_death')
            except:
                pass
            try:
                e.Location = attributes.pop('Place_of_death')
            except:
                pass
            p.Death = e
        return p

if __name__ == '__main__':
    p = Person( Gender='Male', Lastname='Gundu', Alive=True)
    print(list(p.__dict__.values()))
    if None in list(p.__dict__.values()):
        print('None')
