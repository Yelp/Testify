from __future__ import absolute_import
from itertools import chain
from itertools import groupby
from json import loads
import sys
from collections import namedtuple

from . import test_discovery
from .test_runner import TestRunner


def readlines(fileobj):
    while True:
        line = fileobj.readline().rstrip()
        if line:
            yield line
        else:
            return


class Test(namedtuple('TestTuple', ('module', 'cls', 'method'))):
    @classmethod
    def from_json(cls, json):
        json = loads(json)
        return cls.from_name(json['test'])

    @classmethod
    def from_name(cls, name):
        name, _, method = name.rpartition('.')
        module, _, clsname = name.partition(' ')
        return cls(module, clsname, method)


class TestRerunner(TestRunner):
    def __init__(self, *args, **kwargs):
        self.filename = kwargs.pop('rerun_test_file')
        super(TestRerunner, self).__init__(*args, **kwargs)

    def discover(self):
        if self.filename == '-':
            tests = sys.stdin
        else:
            tests = open(self.filename)

        test = tests.readline().rstrip()

        if not test:
            return

        if test.startswith('{'):
            constructor = Test.from_json
        else:
            constructor = Test.from_name

        # Put back the test name we peeked at to choose a constructor
        tests = chain(
            [constructor(test)],
            (
                constructor(test.rstrip())
                for test in readlines(tests)
                if test  # Skip blank lines
            ),
        )

        for class_path, tests in groupby(tests, lambda test: test[:2]):
            module, cls = class_path
            methods = (test.method for test in tests)

            cls = test_discovery.import_test_class(module, cls)
            yield self._construct_test(cls, name_overrides=methods)
