# -*- coding: utf-8 -*-

import os.path
import shutil
import subprocess
import tempfile

import testify as T

test_file_source = """
import testify as T
import always_fails

class AlwaysFailsTestCase(T.TestCase):
    def test_always_fails(self):
        always_fails.run()
"""

always_fails_source = """
def run():
    raise AssertionError('run was not properly mocked out.')
"""

patching_file_source = """
import mock
import always_fails

always_fails.run = lambda: None
"""

TEST_FILE_NAME = 'test_always_fails.py'
ALWAYS_FAILS_NAME = 'always_fails.py'
PATCHING_FILE_NAME = 'patching_file.py'

class StartupModuleTestCase(T.TestCase):

    @T.setup_teardown
    def create_temporary_files(self):
        self.setup_files()
        yield
        self.delete_files()

    def setup_files(self):
        write_file(ALWAYS_FAILS_NAME, always_fails_source)
        write_file(TEST_FILE_NAME, test_file_source)
        write_file(PATCHING_FILE_NAME, patching_file_source)

    def delete_files(self):
        os.remove(ALWAYS_FAILS_NAME)
        os.remove(TEST_FILE_NAME)
        os.remove(PATCHING_FILE_NAME)

    def test_fails_without_initial_module_loading(self):
        ret = subprocess.call('bin/testify ' + TEST_FILE_NAME, shell=True)
        T.assert_not_equal(0, ret, 'The test should not have passed.')

    def test_passes_with_initial_module_loading(self):
        ret = subprocess.call(
            'bin/testify ' + TEST_FILE_NAME + ' --startup-module=' + PATCHING_FILE_NAME, shell=True)
        T.assert_equal(ret, 0, 'The test should have passed, but it failed with a status code of {0}'.format(ret))

def write_file(filename, source):
    with open(filename, 'w') as f:
        f.write(source)

if __name__ == '__main__':
    T.run()
