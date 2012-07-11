"""
Provides the mock_logging context manager.
"""

import itertools
import logging
from contextlib import contextmanager
from testify import assert_any_match_regex
from testify import assert_all_not_match_regex


_mock_loggers = 0


class MockLogger(object):
    def __init__(self):
        global _mock_loggers
        self.log = logging.getLogger("mock_logger%d" % _mock_loggers)
        self.log.propagate = 0
        _mock_loggers += 1
        self.handler = MockHandler()
        self.log.handlers = [self.handler]
        self._fake_handlers = []

    def get(self, level):
        return self.handler.get(level)

    def clear(self):
        return self.handler.clear()

    def __getattr__(self, key):
        return getattr(self.log, key)

    def addHandler(self, handler):
        self._fake_handlers.append(handler)

    @property
    def handlers(self):
        return self._fake_handlers

    @contextmanager
    def assert_logs(self, *args, **kwargs):
        with self.handler.assert_logs(*args, **kwargs):
            yield

    @contextmanager
    def assert_does_not_log(self, *args, **kwargs):
        with self.handler.assert_does_not_log(*args, **kwargs):
            yield

    def assert_logged(self, levels):
        """Assert that this Logger logged something."""
        return self.handler.assert_logged(levels)

    def assert_did_not_log(self, levels):
        """Assert that this Logger logged something."""
        return self.handler.assert_did_not_log(levels)


class MockHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        # logging.Handler is old-style in 2.6
        logging.Handler.__init__(self, *args, **kwargs)
        self.buf = {}

    @contextmanager
    def assert_logs(self, levels=None, log_regex=".*"):
        """Asserts that the given block logs something.

        Args:
        levels -- log level to look for. By default, look at all levels
        log_regex -- regex matching a particular log message to look for. By default,
            any message will match.
        """
        self.clear()
        yield
        self.assert_logged(levels, log_regex)

    def assert_logged(self, levels=None, log_regex=".*"):
        if levels:
            for level in levels:
                assert level in self.buf, 'expected something to be logged in level %r' % level
                assert_any_match_regex(log_regex, self.buf[level])
        else:
            assert self.buf, 'expected something to be logged'
            assert_any_match_regex(log_regex, itertools.chain.from_iterable(self.buf.values()))

    @contextmanager
    def assert_does_not_log(self, levels=None, log_regex=".*"):
        """Asserts that the given block does not log something.

        Args:
        levels -- log level to look for. By default, look at all levels
        log_regex -- regex matching a particular log message to look for. By default,
            any message will match.
        """
        self.clear()
        yield
        self.assert_did_not_log(levels, log_regex)

    def assert_did_not_log(self, levels=None, log_regex=".*"):
        if self.buf is None:
            return
        if levels:
            for level in levels:
                if level in self.buf:
                    assert_all_not_match_regex(log_regex, self.buf[level])
        else:
            assert_all_not_match_regex(log_regex, itertools.chain.from_iterable(self.buf.values()))

    def clear(self):
        self.buf.clear()

    def get(self, level):
        return self.buf.get(level)

    def emit(self, record):
        msg = self.format(record)
        self.buf.setdefault(record.levelno, [])
        self.buf[record.levelno].append(msg)


@contextmanager
def mock_logging(logger_names=[]):
    """Mocks out logging inside the context manager. If a logger name is
    provided, will only mock out that logger. Otherwise, mocks out the root
    logger.

    Not threadsafe.

    Yields a MockHandler object.
    """
    if logger_names:
        queue = [logging.getLogger(logger_name) for logger_name in logger_names]
    else:
        queue = [logging.getLogger('')]
    new_handler = MockHandler()
    previous_handlers = {}
    previous_propagates = {}
    for logger in queue:
        previous_handlers[logger] = logger.handlers[:]
        previous_propagates[logger] = logger.propagate
        logger.handlers = [new_handler]
        logger.propagate = 0
    yield new_handler
    for logger in queue:
        logger.handlers = previous_handlers[logger]
        logger.propagate = previous_propagates[logger]
