import sys
import traceback


class TestReporter(object):
    """Base interface for tracking results of test runs
    
    A TestReporter is configured as a callback for each test case by test_runner.
    """
    def __init__(self, options):
        """Constructor
        
        Args -
            options - The result of  OptionParser which contains, as attributes, all the options for the running program.
        """
        self.options = options

    def test_start(self, test_case, method):
        """Called when a test method is being run."""
        pass

    def test_complete(self, test_case, result):
        """Called when a test case is complete"""
        pass

    def report(self):
        """Called at the end of the test run to report results"""
        pass

