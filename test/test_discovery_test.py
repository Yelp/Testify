
from functools import wraps
from os import chdir
from os import getcwd
from os.path import abspath
from os.path import dirname
from os.path import join

from testify import assert_length
from testify import assert_raises
from testify import run
from testify import TestCase
from testify import test_discovery


HERE = dirname(abspath(__file__))

class DiscoveryTestCase(TestCase):
    def discover(self, path):
        # Exhaust the generator to catch exceptions
        return [mod for mod in test_discovery.discover(path)]

def relative(func):
    'decorator for tests that rely on relative paths'
    @wraps(func)
    def wrapped(*args, **kwargs):
        cwd = getcwd()
        chdir(HERE)
        try:
            return func(*args, **kwargs)
        finally:
            # clean up even after test failures
            chdir(cwd)
    return wrapped

class TestDiscoverDottedPath(DiscoveryTestCase):
    @relative
    def test_dotted_path(self):
        assert self.discover('test_suite_subdir.define_testcase')

class TestDiscoverFilePath(DiscoveryTestCase):
    @relative
    def test_file_path(self):
        assert self.discover('test_suite_subdir/define_testcase')

    @relative
    def test_file_path_with_py_suffix(self):
        assert self.discover('test_suite_subdir/define_testcase.py')

    @relative
    def test_file_path_with_non_normal_path(self):
        assert self.discover('./test_suite_subdir///define_testcase.py')

    def test_file_absolute_path(self):
        assert self.discover(join(HERE, 'test_suite_subdir/define_testcase.py'))


class TestDiscoverIgnoreImportedThings(DiscoveryTestCase):
    @relative
    def test_imported_things_are_ignored(self):
        #TODO CHANGE MY NAME
        discovered_imported = list(test_discovery.discover('test_suite_subdir.import_testcase'))
        discovered_actually_defined_in_module = list(test_discovery.discover('test_suite_subdir.define_testcase'))

        assert_length(discovered_imported, 0)
        assert_length(discovered_actually_defined_in_module, 1)


class ImportTestClassCase(DiscoveryTestCase):

    def discover(self, module_path, class_name):
        return test_discovery.import_test_class(module_path, class_name)

    @relative
    def test_discover_testify_case(self):
        assert self.discover('test_suite_subdir.define_testcase', 'DummyTestCase')

    @relative
    def test_discover_unittest_case(self):
        assert self.discover('test_suite_subdir.define_unittestcase', 'TestifiedDummyUnitTestCase')

    @relative
    def test_discover_bad_case(self):
        assert_raises(test_discovery.DiscoveryError, self.discover, 'bad.subdir', 'DummyTestCase')
        assert_raises(test_discovery.DiscoveryError, self.discover, 'test_suite_subdir.define_testcase', 'IGNORE ME')


if __name__ == '__main__':
    run()

# vim: set ts=4 sts=4 sw=4 et:
