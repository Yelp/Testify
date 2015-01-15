from os.path import abspath

from testify import assert_length
from testify import assert_raises
from testify import run
from testify import TestCase
from testify import test_discovery


class DiscoveryTestCase(TestCase):
    def discover(self, path):
        # Exhaust the generator to catch exceptions
        return [mod for mod in test_discovery.discover(path)]


class TestDiscoverDottedPath(DiscoveryTestCase):
    def test_dotted_path(self):
        assert self.discover('test.test_suite_subdir.define_testcase')


class TestDiscoverFilePath(DiscoveryTestCase):
    def test_file_path(self):
        assert self.discover('test/test_suite_subdir/define_testcase')

    def test_file_path_with_py_suffix(self):
        assert self.discover('test/test_suite_subdir/define_testcase.py')

    def test_file_path_with_non_normal_path(self):
        assert self.discover('./test/test_suite_subdir///define_testcase.py')

    def test_file_absolute_path(self):
        assert self.discover(abspath('test/test_suite_subdir/define_testcase.py'))


class TestDiscoverIgnoreImportedThings(DiscoveryTestCase):
    def test_imported_things_are_ignored(self):
        discovered_imported = list(test_discovery.discover('test.test_suite_subdir.import_testcase'))
        discovered_actually_defined_in_module = list(test_discovery.discover('test.test_suite_subdir.define_testcase'))

        assert_length(discovered_imported, 0)
        assert_length(discovered_actually_defined_in_module, 1)


class ImportTestClassCase(DiscoveryTestCase):

    def discover(self, module_path, class_name):
        return test_discovery.import_test_class(module_path, class_name)

    def test_discover_testify_case(self):
        assert self.discover('test.test_suite_subdir.define_testcase', 'DummyTestCase')

    def test_discover_unittest_case(self):
        assert self.discover('test.test_suite_subdir.define_unittestcase', 'TestifiedDummyUnitTestCase')

    def test_discover_bad_case(self):
        assert_raises(test_discovery.DiscoveryError, self.discover, 'bad.subdir', 'DummyTestCase')
        assert_raises(test_discovery.DiscoveryError, self.discover, 'test.test_suite_subdir.define_testcase', 'IGNORE ME')


if __name__ == '__main__':
    run()

# vim: set ts=4 sts=4 sw=4 et:
