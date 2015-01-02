# Copyright 2011 Yelp
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import random


def add_command_line_options(parser):
    parser.add_option(
        "--seed",
        action="store",
        dest="seed",
        type='int',
        default=None,
        help=(
            "Seed random for each test using this value + hash of the "
            "testclass' name. This allows tests to have random yet "
            "reproducible numbers."
        ),
    )


def run_test_case(options, test_case, runnable):
    # If random seed is set, seed with seed value plus hash(testclass name). This makes random tests at least be reproducible,
    # and rerunning with another seed (eg. timestamp) will let repeated runs use random values.
    if options.seed:
        random.seed(options.seed + hash(test_case.__class__.__name__))
    return runnable()
