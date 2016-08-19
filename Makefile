.PHONY: test
test:
	tox

.PHONY: clean
clean:
	rm -rf build/ MANIFEST
	find . -name '*.pyc' -delete
	find . -name "._*" -delete
