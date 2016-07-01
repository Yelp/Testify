class Testify(Exception):
    pass


class TestifyError(Testify):
    pass


class DiscoveryError(TestifyError):
    pass


class Interruption(Testify):
    pass
