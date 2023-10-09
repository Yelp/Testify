from setuptools import setup

setup(
    name="testify",
    version="0.11.3",
    provides=["testify"],
    author="Yelp",
    author_email="yelplabs@yelp.com",
    url="http://github.com/Yelp/Testify",
    description='Testing framework',
    classifiers=[
        "Programming Language :: Python",
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: Implementation :: CPython',
        "Operating System :: OS Independent",
        "License :: OSI Approved :: Apache Software License",
        "Topic :: Software Development :: Testing",
        "Intended Audience :: Developers",
        "Development Status :: 4 - Beta",
    ],
    install_requires=['mock', 'six>=1.7.3'],
    python_requires='>=3.8',
    packages=["testify", "testify.contrib", "testify.utils", "testify.plugins"],
    scripts=['bin/testify'],
    long_description="""Testify - A Testing Framework

Testify is a replacement for Python's unittest module and nose. It is modeled after unittest, and tests written for unittest
will run under testify with a minimum of adjustments, but it has features above and beyond unittest:

  - class-level setup and teardown fixture methods which are run once each for an entire set of test methods.
  - a decorator-based approach for fixture methods, eliminating the need for super() calls.
  - More pythonic, less java
  - enhanced test discovery - testify can drill down into packages to find test cases (similiar to nose).
  - support for collecting and running tests by collecting modules, classes or methods into test suites.
  - Pretty test runner output (color!)
  - Extensible plugin system for adding additional functionality around reporting
  - Comes complete with other handy testing utilities: Mocking (turtle), code coverage integration and profiling.
"""
)
