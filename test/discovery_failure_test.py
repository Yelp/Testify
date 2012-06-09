import os
import tempfile

from testify.test_logger import _log
from testify import TestCase, assert_in, run, setup, teardown, test_discovery
from testify.test_discovery import DiscoveryError


class BrokenImportTestCase(TestCase):
    @setup
    def create_broken_import_file(self):
        """Write out a test file containing a bad import. This way, a broken
        test isn't lying around to be discovered while running other tests.
        Write the file in the directory containing this test file; otherwise,
        Testify will refuse to import it."""
        here = os.path.dirname(os.path.abspath(__file__))
        (unused_filehandle, self.broken_import_file_path) = tempfile.mkstemp(
            prefix='fake_broken_import',
            suffix='.py',
            dir=here,
        )
        with open(self.broken_import_file_path, 'w') as broken_import_file:
            broken_import_file.write('import non_existent_module')
        self.broken_import_module = 'test.%s' % os.path.splitext(os.path.basename(self.broken_import_file_path))[0]

    @teardown
    def delete_broken_import_file(self):
        files = [
            self.broken_import_file_path,
            # Also remove the .pyc that was created if the file was imported.
            self.broken_import_file_path + 'c',
        ]
        for f in files:
            try:
                os.remove(f)
            except OSError, exc:
                _log.error("Could not remove broken import file %s: %r" % (f, exc))


class DiscoveryFailureTestCase(BrokenImportTestCase):
    def test_discover_test_with_broken_import(self):
        """Insure that DiscoveryError is raised when a test which imports a
        non-existent module is discovered."""
        try:
            discovered_tests = test_discovery.discover(self.broken_import_module)
            discovered_tests.next()
        except DiscoveryError, exc:
            assert_in('No module named non_existent_module', str(exc))
        else:
            assert False, 'Expected DiscoveryError.'


if __name__ == '__main__':
    run()

# vim: set ts=4 sts=4 sw=4 et:
