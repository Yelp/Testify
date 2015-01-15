from __future__ import absolute_import
from __future__ import unicode_literals

import io
import os
import shutil
import subprocess
import tempfile

import testify as T
from test.test_case_test import RegexMatcher


def cmd_output(*cmd, **kwargs):
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs
    )
    stdout, stderr = proc.communicate()
    assert proc.returncode != 0, (proc.returncode, stdout, stderr)
    return stdout.decode('UTF-8'), stderr.decode('UTF-8')


class BrokenImportTestCase(T.TestCase):
    __test__ = False

    _mod_counter = 1

    broken_contents = 'import non_existent_module\n'

    def _write_broken_import_file(self):
        BrokenImportTestCase._mod_counter += 1
        self.broken_import_module = '_fake_test_{0}'.format(
            BrokenImportTestCase._mod_counter,
        )
        filename = self.broken_import_module + '.py'
        with io.open(filename, 'w') as test_file:
            test_file.write(self.broken_contents)

    @T.class_setup_teardown
    def create_temporary_directory(self):
        self.tempdir = tempfile.mkdtemp()
        cwd = os.getcwd()
        os.chdir(self.tempdir)
        self._write_broken_import_file()
        try:
            yield
        finally:
            os.chdir(cwd)
            shutil.rmtree(self.tempdir)


class DiscoveryFailureTestCase(BrokenImportTestCase):
    def test_discover_test_with_broken_import(self):
        """Insure that DiscoveryError is raised when a test which imports a
        non-existent module is discovered."""

        stdout, stderr = cmd_output(
            'python', '-m', 'testify.test_program', self.broken_import_module,
        )

        T.assert_equal(
            stdout,
            RegexMatcher(
                r'DISCOVERY FAILURE!\n'
                r'There was a problem importing one or more tests:\n\n'
                r'    Traceback \(most recent call last\):\n'
                r'      File .+, line \d+, in discover\n'
                r"        mod = __import__\(what, fromlist=\[str\(\'__trash\'\)\]\)\n"
                r'      File .+, line \d+, in <module>\n'
                r'        import non_existent_module\n'
                r"    ImportError: No module named '?non_existent_module'?\n\n"
                r"No tests were discovered \(tests must subclass TestCase and test methods must begin with 'test'\).\n"
                r'ERROR.  0 tests / 0 cases: 0 passed, 0 failed.  \(Total test time \d+\.\d+s\)\n'
            ),
        )

        T.assert_equal(
            stderr,
            RegexMatcher(
                r'Traceback \(most recent call last\):\n'
                r'  File .+, line \d+, in discover\n'
                r"    mod = __import__\(what, fromlist=\[str\(\'__trash\'\)\]\)\n"
                r'  File .+, line \d+, in <module>\n'
                r'    import non_existent_module\n'
                r"ImportError: No module named '?non_existent_module'?\n"
            ),
        )


class DiscoveryFailureUnknownErrorTestCase(BrokenImportTestCase):
    broken_contents = 'raise AttributeError("aaaaa!")\n'

    def test_discover_test_with_unknown_import_error(self):
        """Insure that DiscoveryError is raised when a test which raises an unusual exception upon import is discovered."""
        stdout, stderr = cmd_output(
            'python', '-m', 'testify.test_program', self.broken_import_module,
        )
        T.assert_in('DISCOVERY FAILURE', stdout)
        T.assert_in('AttributeError: aaaaa!', stderr)

if __name__ == '__main__':
    T.run()

# vim: set ts=4 sts=4 sw=4 et:
