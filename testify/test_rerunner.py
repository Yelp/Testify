from itertools import groupby
import logging
import os
import sys

from test_runner import TestRunner
from test_runner import TestRunnerException

class TestRerunner(TestRunner):
    """A test runner which discovers tests from a filename listing the tests
    to run.
    """

    def __init__(self, *args, **kwargs):
        filename = kwargs.pop('rerun_test_file')
        self.rerun_test_file = self._get_test_file(filename)
        super(TestRerunner, self).__init__(*args, **kwargs)

    def _get_test_file(self, filename):
        if filename == '-':
            return sys.stdin

        if os.path.isfile(filename):
            return open(filename)

        raise TestRunnerException("Unable to find test file %s" % filename)

    def discover(self):
        for class_path, lines in groupby(self.rerun_test_file, lambda line: line.rpartition('.')[0]):
            if not class_path:
                # Skip blank lines
                continue
            methods = [line.rpartition('.')[2].strip() for line in lines]
            module_path, _, class_name = class_path.partition(' ')

            module = __import__(module_path)
            for part in module_path.split('.')[1:]:
                try:
                    module = getattr(module, part)
                except AttributeError:
                    logging.error("discovery(%s) failed: module %s has no attribute %r" % (module_path, module, part))

            klass = getattr(module, class_name)
            yield klass(name_overrides=methods)
        self.close()

    def close(self):
        if self.rerun_test_file != sys.stdin:
            self.rerun_test_file.close()
