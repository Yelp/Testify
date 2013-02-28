PYTHON=`which python`
DESTDIR=/
PROJECT=python-testify
BUILDIR=$(CURDIR)/debian/$PROJECT
VERSION=`$(PYTHON) setup.py --version`

all:
		@echo "make source - Create source package"
		@echo "make install - Install on local system"
		@echo "make buildrpm - Generate a rpm package"
		@echo "make builddeb - Generate a deb package"
		@echo "make clean - Get rid of scratch and byte files"

source:
		$(PYTHON) setup.py sdist $(COMPILE)

install:
		$(PYTHON) setup.py install --root $(DESTDIR) $(COMPILE)

buildrpm:
		$(PYTHON) setup.py bdist_rpm --post-install=rpm/postinstall --pre-uninstall=rpm/preuninstall

builddeb:
		# build the source package in the parent directory
		# then rename it to project_version.orig.tar.gz
		$(PYTHON) setup.py sdist $(COMPILE) --dist-dir=../ --prune
		rename -f 's/$(PROJECT)-(.*)\.tar\.gz/$(PROJECT)_$$1\.orig\.tar\.gz/' ../*
		# build the package
		dpkg-buildpackage -i -I -rfakeroot

clean:
		$(PYTHON) setup.py clean
		fakeroot $(MAKE) -f $(CURDIR)/debian/rules clean
		rm -rf build/ MANIFEST
		find . -name '*.pyc' -delete
		find . -name "._*" -delete

test:
	PYTHONPATH=. $(PYTHON) ./bin/testify --verbose --summary test

.PHONY: test
