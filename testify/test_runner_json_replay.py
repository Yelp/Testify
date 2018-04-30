from __future__ import absolute_import

import json
import sys

from .test_runner import TestRunner


class TestRunnerJSONReplay(TestRunner):
    """A fake test runner that loads a one-dict-per-line JSON file and sends each dict to the test reporters."""

    def __init__(self, *args, **kwargs):
        self.replay_json = kwargs.pop('replay_json')
        self.replay_json_inline = kwargs.pop('replay_json_inline')

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

        for result in self.results:
            for reporter in self.test_reporters:
                reporter.test_start(result)
                reporter.test_complete(result)

        report = [reporter.report() for reporter in self.test_reporters]
        return all(report)

    def loadlines(self):
        lines = []
        if self.replay_json_inline:
            lines.extend(self.replay_json_inline)

        if self.replay_json:
            f = open(self.replay_json)
            lines.extend(f.readlines())
        else:
            lines.append("RUN COMPLETE")

        assert lines, "No JSON data found."

        results = []
        for line in lines:
            if line.strip() == "RUN COMPLETE":
                continue
            try:
                results.append(json.loads(line.strip()))
            except Exception:
                sys.exit("Invalid JSON line: %r" % line.strip())

        if lines[-1].strip() != "RUN COMPLETE":
            sys.exit("Incomplete run detected")

        return results
