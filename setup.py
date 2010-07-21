from distutils.core import setup

setup(
    name="testify",
    version='0.1.3',
	provides="testify",
    author="Yelp",
    author_email="opensource@yelp.com",
    url="http://github.com/Yelp/testify",
    description='Testing framework',
    classifiers=[
        "Programming Language :: Python",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: Apache Software License",
        "Topic :: Software Development :: Testing",
        "Intended Audience :: Developers",
        "Development Status :: 4 - Beta",
    ],
    packages=["testify", "testify.utils"],
	scripts=['bin/testify'],
	long_description="""\
Testify is a replacement for Python's unittest module.  It is modeled after unittest, and tests written for unittest will run under testify with a minimum of adjustments, but it has features above and beyond unittest:

  - class-level setup and teardown fixture methods which are run once each for an entire set of test methods.
  - a decorator-based approach for fixture methods, eliminating the need for super() calls.
  - More pythonic, less java-unittest
  - enhanced test discovery - testify can drill down into packages to find test cases.
  - support for collecting and running tests by 'tagging' modules, classes or methods.
  - A decorator-based approach to temporarily disabling certain tests, which strongly encourages documentation and eventual fixing of bugs.
  - Pretty test runner output (color!)
	"""
)
