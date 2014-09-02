import sys

import testify as T
import testify.plugins.mock_imports as mock_imports
from testify.test_runner import TestRunner
from testify import assert_in

IMPORT = 'test.plugins.import_tests.import_me'

class Object(object):
    pass

class MockImportsTestCase(T.TestCase):
    def test_runner_import(self):
        class DummyTestCase(T.TestCase):
            def test_foo(self):
                pass

        options = Object()
        options.mock_importing_module = IMPORT
        runner = TestRunner(DummyTestCase, plugin_modules=[mock_imports], options=options)
        runner.run()
        assert_in(IMPORT, map(lambda mod: mod.__name__ if mod else None, sys.modules.values()))

