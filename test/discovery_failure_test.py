from __future__ import absolute_import
from __future__ import unicode_literals

import subprocess

import testify as T
from test.test_case_test import RegexMatcher
from testify import exit


def cmd_output(*cmd, **kwargs):
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs
    )
    stdout, stderr = proc.communicate()
    assert proc.returncode == exit.DISCOVERY_FAILED, (proc.returncode, stdout, stderr)
    return stdout.decode('UTF-8'), stderr.decode('UTF-8')


class DiscoveryFailureTestCase(T.TestCase):
    def test_discover_test_with_broken_import(self):
        """Ensure that DiscoveryError is raised when a test which imports a
        non-existent module is discovered."""

        stdout, stderr = cmd_output(
            'python', '-m', 'testify.test_program', 'discovery_error', cwd='examples',
        )

        T.assert_equal(
            stdout,
            RegexMatcher(
                r'test1\n'
                r'\.DISCOVERY FAILURE!\n'
                r'There was a problem importing one or more tests:\n\n'
                r'    Traceback \(most recent call last\):\n'
                r'      File "[^"]+", line \d+, in discover\n'
                r'        submod = __import__\(module_name, fromlist=\[str\(\'__trash\'\)\]\)\n'
                r'(                 \^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^'
                r'\^\^\^\^\n)?'
                r'      File "[^"]+", line \d+, in <module>\n'
                r'        import non_existent_module  \# noqa: F401\n'
                r'(        \^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\n)?'
                r'    (ModuleNotFoundError|ImportError): No module named \'?non_existent_module\'?\n'
            ),
        )

        # TODO: fix this runpy warning
        if 'found in sys.modules' in stderr.splitlines()[0]:
            stderr = ''.join(stderr.splitlines(True)[2:])

        T.assert_equal(
            stderr,
            RegexMatcher(
                r'(Traceback \(most recent call last\):\n)?'
                r'  File .+, line \d+, in discover\n'
                r"    submod = __import__\(module_name, fromlist=\[str\(\'__trash\'\)\]\)\n"
                r'(             \^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^'
                r'\^\^\n)?'
                r'  File .+, line \d+, in <module>\n'
                r'    import non_existent_module  \# noqa: F401\n'
                r'(    \^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\^\n)?'
                r"(ModuleNotFoundError|ImportError): No module named '?non_existent_module'?\n"
            ),
        )


class DiscoveryFailureUnknownErrorTestCase(T.TestCase):
    def test_discover_test_with_unknown_import_error(self):
        """Insure that DiscoveryError is raised when a test which raises an unusual exception upon import is discovered."""
        stdout, stderr = cmd_output(
            'python', '-m', 'testify.test_program', 'attribute_error', cwd='examples',
        )
        T.assert_in('DISCOVERY FAILURE', stdout)
        # FIXME: let's not print the errror twice -- just on stderr
        T.assert_in('AttributeError: aaaaa!', stderr)
        T.assert_in('AttributeError: aaaaa!', stdout)


if __name__ == '__main__':
    T.run()

# vim: set ts=4 sts=4 sw=4 et:
