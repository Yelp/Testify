from __future__ import with_statement

import logging
import os
import tempfile

from testify import TestCase, assert_in, class_setup, class_teardown, run, test_discovery
from testify.test_discovery import DiscoveryError

_log = logging.getLogger('testify')

class BrokenImportTestCase(TestCase):
    __test__ = False

    def create_broken_import_file(self, contents='import non_existent_module'):
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
            broken_import_file.write(contents)
        self.broken_import_module = 'test.%s' % os.path.splitext(os.path.basename(self.broken_import_file_path))[0]

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

    @class_setup
    def setup_import_file(self):
        self.create_broken_import_file()

    @class_teardown
    def teardown_import_file(self):
        self.delete_broken_import_file()


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


class DiscoveryFailureUnknownErrorTestCase(BrokenImportTestCase):
    @class_setup
    def setup_import_file(self):
        self.create_broken_import_file(contents='raise AttributeError("aaaaa!")')

    def test_discover_test_with_unknown_import_error(self):
        """Insure that DiscoveryError is raised when a test which raises an unusual exception upon import is discovered."""

        try:
            discovered_tests = test_discovery.discover(self.broken_import_module)
            discovered_tests.next()
        except DiscoveryError, exc:
            assert_in('Got unknown error when trying to import', str(exc))
        else:
            assert False, 'Expected DiscoveryError.'

if __name__ == '__main__':
    run()

# vim: set ts=4 sts=4 sw=4 et:
