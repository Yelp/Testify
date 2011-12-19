from itertools import groupby
import logging
import sys

from test_runner import TestRunner

class TestRerunner(TestRunner):
    def __init__(self, *args, **kwargs):
        filename = kwargs.pop('rerun_test_file')
        if filename == '-':
            self.rerun_test_file = sys.stdin
        else:
            self.rerun_test_file = open(filename)
        super(TestRerunner, self).__init__(*args, **kwargs)

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
