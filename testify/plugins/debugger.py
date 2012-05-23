# Copyright 2009 Yelp
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
def add_command_line_options(parser):
	parser.add_option("-d", "--ipdb", action="store_true", dest="debugger")

def run_test_case(options, test_case, runnable):
	if options.debugger:
		try:
			return runnable()
		except:
			import ipdb, sys, traceback
			e, m, tb = sys.exc_info()
			traceback.print_exception(tb)
			ipdb.post_mortem(tb)
	else:
		return runnable()
