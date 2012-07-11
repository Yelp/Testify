"""
Provides the mock_logging context manager.
"""

import itertools
import logging
from contextlib import contextmanager
from testify import assert_any_match_regex
from testify import assert_all_not_match_regex


class MockHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        # logging.Handler is old-style in 2.6
        logging.Handler.__init__(self, *args, **kwargs)
        self.buf = {}

    @contextmanager
    def assert_logs(self, levels=None, log_regex=".*"):
        """Asserts that the given block will log some messages.

        Args:
          levels -- log level to look for. By default, look at all levels
          log_regex -- regex matching a particular log message to look for. By default,
            any message will match.
        """
        self.clear()
        yield
        self.assert_logged(levels, log_regex)

    def assert_logged(self, levels=None, log_regex=".*"):
        """Asserts that the mock hander did log some messages.

        Args:
          levels -- log level to look for. By default, look at all levels
          log_regex -- regex matching a particular log message to look for. By default,
            any message will match.
        """
        if levels:
            for level in levels:
                assert level in self.buf, 'expected something to be logged in level %r' % level
                assert_any_match_regex(log_regex, self.buf[level])
        else:
            assert self.buf, 'expected something to be logged'
            assert_any_match_regex(log_regex, itertools.chain.from_iterable(self.buf.values()))

    @contextmanager
    def assert_does_not_log(self, levels=None, log_regex=".*"):
        """Asserts that the given block will not log some messages.

        Args:
          levels -- log level to look for. By default, look at all levels
          log_regex -- regex matching a particular log message to look for. By default,
            any message will match.
        """
        self.clear()
        yield
        self.assert_did_not_log(levels, log_regex)

    def assert_did_not_log(self, levels=None, log_regex=".*"):
        """Asserts that the mock handler did not log some messages.

        Args:
          levels -- log level to look for. By default, look at all levels
          log_regex -- regex matching a particular log message to look for. By default,
            any message will match.
        """
        if self.buf is None:
            return
        if levels:
            for level in levels:
                if level in self.buf:
                    assert_all_not_match_regex(log_regex, self.buf[level])
        else:
            assert_all_not_match_regex(log_regex, itertools.chain.from_iterable(self.buf.values()))

    def clear(self):
        """Clear all logged messages.
        """
        self.buf.clear()

    def get(self, level):
        """Get all messages logged for a certain level.
        Returns a list of messages for the given level.
        """
        return self.buf.get(level)

    def emit(self, record):
        """Handles emit calls from logging, stores the logged record in an internal list that is
        accessible via MockHandler.get.
        """
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

    Example;

        with mock_logging() as mock_handler:
            logging.info("event")
            assert_equal(["event"], mock_handler.get(logging.INFO))


        with mock_logging(['subsystem']) as mock_handler:
            logging.getLogger('subsystem').info("event")
            assert_equal(["event"], mock_handler.get(logging.INFO))

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
