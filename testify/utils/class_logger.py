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


import logging


class ClassLogger(object):
    """Descriptor that returns a logger for a class named module.class

    Expected Usage:
        class MyClass(object):
            ...
            log = ClassLogger()

            def my_method(self):
                self.log.debug('some debug message')
                # should log something like: mymodule.MyClass 'some debug message'
    """

    def __get__(self, obj, obj_type=None):
        object_class = obj_type or obj.__class__
        name = 'testify.%s.%s' % (object_class.__module__, object_class.__name__)
        return logging.getLogger(name)
