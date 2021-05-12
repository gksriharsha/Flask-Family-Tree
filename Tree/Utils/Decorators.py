def cached(function):
    def wrapper():
        function()

    return wrapper


def log_this(function):
    def wrapper():
        function()

    return wrapper
