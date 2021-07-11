import requests
from bs4 import BeautifulSoup


class InvalidCoordinateException(Exception):
    pass


def getCoordinates(Place, State):
    html_doc = requests.get(
        f'https://www.google.com/search?q=latitude+and+longitude+of+{Place}%2C+{State.replace(" ", "+")}').text
    soup = BeautifulSoup(html_doc, 'html.parser')
    divs = soup.find_all("div", {"class": "BNeawe iBp4i AP7Wnd"})
    coords = divs[1].text.split(',')
    numbers = [-1 * eval(coord[:-3]) if 'S' in coord or 'W' in coord else eval(coord[:-3]) for coord in coords]
    if isinstance(numbers[0], float) and isinstance(numbers[1], float):
        return numbers
    else:
        raise InvalidCoordinateException


if __name__ == "__main__":
    getCoordinates('Los Angeles', 'California')
