
import json
from test_runner import TestRunner

class TestRunnerJSONReplay(TestRunner):
    """A fake test runner that loads a one-dict-per-line JSON file and sends each dict to the test reporters."""
    def __init__(self, *args, **kwargs):
        self.replay_json = kwargs.pop('replay_json')

        self.results = self.loadlines()

        super(TestRunnerJSONReplay, self).__init__(*args, **kwargs)

    def discover(self):
        """No-op because this class runs no tests"""
        pass

    def run(self):
        """Replays the results given.
        Reports the test counts, each test result, and calls .report() for all test reporters."""
        test_cases = set()
        test_methods = set()

        for result in self.results:
            test_cases.add((result['method']['module'], result['method']['class'],))
            test_methods.add((result['method']['module'], result['method']['class'], result['method']['name'],))

        for reporter in self.test_reporters:
            reporter.test_counts(len(test_cases), len(test_methods))

        for result in self.results:
            for reporter in self.test_reporters:
                reporter.test_start(result)
                reporter.test_complete(result)


        for reporter in self.test_reporters:
            reporter.report()

    def loadlines(self):
        f = open(self.replay_json)
        results = []
        lines = f.readlines()
        for line in lines:
            if line.strip() == "RUN COMPLETE":
                continue
            try:
                results.append(json.loads(line.strip()))
            except:
                print 'Skipping invalid line: %s' % line

        if lines and lines[-1].strip() != "RUN COMPLETE":
            raise Exception("Incomplete run detected")

        return results