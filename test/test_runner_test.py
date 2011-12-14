import imp
from testify import test_case, test_runner, setup

prepared = False
running = False

def prepare_test_case(options, test_case):
    global prepared
    prepared = True

def run_test_case(options, test_case, runnable):
    global running
    running = True
    try:
        return runnable()
    finally:
        running = False


class PluginTestCase(test_case.TestCase):
    """Verify plugin support

    This is pretty complex and deserves some amount of explanation.
    What we're doing here is creating a module object on the fly (our plugin) and a
    test case class so we can call runner directly and verify the right parts get called.

    If you have a failure in here the stack is going to look crazy because we are a test case, being called by
    a test running, which is building and running ANOTHER test runner to execute ANOTHER test case. Cheers.
    """
    @setup
    def build_module(self):
        self.our_module = imp.new_module("our_module")
        setattr(self.our_module, "prepare_test_case", prepare_test_case)
        setattr(self.our_module, "run_test_case", run_test_case)

    @setup
    def build_test_case(self):
        self.ran_test = False
        class DummyTestCase(test_case.TestCase):
            def test(self_):
                self.ran_test = True
                assert self.our_module.prepared
                assert self.our_module.running

        self.dummy_test_class = DummyTestCase

    def test_plugin_run(self):
        runner = test_runner.TestRunner(self.dummy_test_class, plugin_modules=[self.our_module])

        assert runner.run()
        assert self.ran_test
        assert not running
        assert prepared


