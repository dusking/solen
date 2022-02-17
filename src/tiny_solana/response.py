class Response:
    def __init__(self, ok=None, err=None):
        self.ok = ok
        self.err = err


class Ok(Response):
    def __init__(self, value):
        super(Ok, self).__init__(ok=value)


class Err(Response):
    def __init__(self, value):
        super(Err, self).__init__(err=value)
