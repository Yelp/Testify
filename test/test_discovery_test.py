from testify import TestCase, run, test_discovery

class DiscoveryTestCase(TestCase):
    def discover(self, path):
        # Exhause the generator to catch exceptons
        [mod for mod in test_discovery.discover(path)]

class TestDiscoverDottedPath(DiscoveryTestCase):
    def test_dotted_path(self):
        self.discover('subdir.test')

class TestDiscoverFilePath(DiscoveryTestCase):
    def test_file_path(self):
        self.discover('subdir/test')

    def test_file_path_with_py_suffix(self):
        self.discover('subdir/test.py')


if __name__ == '__main__':
    run()
