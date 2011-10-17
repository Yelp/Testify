from test_runner import TestRunner
import urllib2
try:
    import simplejson as json
    _hush_pyflakes = [json]
    del _hush_pyflakes
except ImportError:
    import json


class TestRunnerClient(TestRunner):
    def __init__(self, *args, **kwargs):
        self.connect_addr = kwargs.pop('connect_addr')
        super(TestRunnerClient, self).__init__(*args, **kwargs)

    def discover(self):
        finished = False
        while not finished:
            class_path, methods, finished = self.get_next_tests()
            if class_path and methods:
                module_path, _, class_name = class_path.partition(' ')

                module = __import__(module_path)
                for part in module_path.split('.')[1:]:
                    try:
                        module = getattr(module, part)
                    except AttributeError:
                        print "discovery(%s) failed: module %s has no attribute %r" % (module_path, module, part)

                klass = getattr(module, class_name)
                yield {'class': klass, 'methods': methods}

    def get_next_tests(self):
        response = urllib2.urlopen('http://%s/tests?runner=test' % self.connect_addr)
        d = json.load(response)
        return (d.get('class'), d.get('methods'), d['finished'])