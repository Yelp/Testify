#!/usr/local/bin/python

__author__="lenza"
__date__ ="$May 25, 2009"

"""This is a module for gathing code coverage information.
Use coverage.start() to begin collecting information, and coverage.stop() to end collection.
See https://trac.yelpcorp.com/wiki/TestingCoverage for more information
"""

import sys

class FakeCoverage:
    warning_printed = False

    @classmethod
    def start(cls):
        if not cls.warning_printed:
            print >>sys.stderr, "*** WARNING: To gather coverage information you must install the Python coverage package."
            print >>sys.stderr, "See: http://pypi.python.org/pypi/coverage/"
            cls.warning_printed = True

    @staticmethod
    def stop(): pass

    @staticmethod
    def save(): pass

try:
    import coverage
    _hush_pyflakes = [coverage]
    del _hush_pyflakes
except (ImportError, NameError), ex:
    coverage = None

started = False
coverage_instance = None

def start(testcase_name = None):
    global started
    global coverage_instance
    assert not started
    if coverage is not None:
        coverage_instance = coverage.coverage(data_file="coverage_file.", data_suffix=testcase_name, auto_data=True)
    else:
        coverage_instance = FakeCoverage()

    coverage_instance.start()
    started = True

def stop():
    global started
    global coverage_instance
    assert started
    coverage_instance.stop()
    coverage_instance.save()
    started = False

if __name__ == "__main__":
    if coverage is None:
        print """You must install the Python coverage 3.0.b3 package to use coverage.\nhttp://pypi.python.org/pypi/coverage/"""
        quit()

    if len(sys.argv) < 2:
        print "Usage: python code_coverage.py output_directory <diff>"
        quit()

    if len(sys.argv) > 2:
        diff_file = sys.argv[2]
    else:
        diff_file = None

    directory = sys.argv[1]
    coverage_instance = coverage.coverage(data_file="coverage_file.", auto_data=True)
    coverage_instance.exclude("^import")
    coverage_instance.exclude("from.*import")
    coverage_instance.combine()
    if diff_file is None:
        coverage_instance.html_report(morfs=None, directory=directory, ignore_errors=False, omit_prefixes=None)
    else:
        coverage_instance.svnhtml_report(morfs=None, directory=directory, ignore_errors=False, omit_prefixes=None, filename=diff_file)

    #coverage_result = coverage_entry_point()
    #sys.exit(coverage_result)

