import sys

from doctest import DocTestFinder, DocTestRunner, REPORT_NDIFF
from StringIO import StringIO
from testify import MetaTestCase, TestCase
from types import MethodType

class DocMetaTestCase(MetaTestCase):
	"""See DocTestCase for documentation."""
	def __init__(cls, name, bases, dct):
		super(DocMetaTestCase, cls).__init__(name, bases, dct)

		try:
			module = dct['module']
		except KeyError:
			if dct.get('__test__', True) == False:
				# This is some kind of abstract class. Do nothing.
				return
			else:
				raise ValueError('No module was given for doctest search!')

		globs = dct.get('globs', None)
		extraglobs = dct.get('extraglobs', None)

		if isinstance(module, basestring):
			# transform a module name into a module
			module = sys.modules[module]

		for doctest in DocTestFinder(recurse=True).find(module, name='test_doc', globs=globs, extraglobs=extraglobs):
			cls.add_test(doctest)

	def add_test(cls, doctest):
		"add a test to this TestCase"
		if not doctest.examples:
			# There's no tests in this doctest. Don't bother.
			return

		test = lambda self: run_test(doctest)

		# Need to change dots to colons so that testify doesn't try to interpret them.
		testname = doctest.name.replace('.', ':')
		test.__name__ = doctest.name = testname

		test = MethodType(test, None, cls)
		vars(test)['_suites'] = set()

		setattr(cls, test.__name__, test)

def run_test(doctest):
	summary = StringIO()
	runner = DocTestRunner(optionflags=REPORT_NDIFF)
	runner.run(doctest, out=summary.write)

	assert runner.failures == 0, '\n' + summary.getvalue()

class DocTestCase(TestCase):
	"""
	A testify TestCase that turns doctests into unit tests.

	Subclass attributes:
		module -- the module object to be introspected for doctests
		globs -- (optional) a dictionary containing the initial global variables for the tests.
			A new copy of this dictionary is created for each test.
		extraglobs -- (optional) an extra set of global variables, which is merged into globs.
	"""
	__metaclass__ = DocMetaTestCase
	__test__ = False
