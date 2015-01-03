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

"""Mocking and Stubbing framework

This framework is built around the 'Turtle' object. A Turtle object returns another turtle for every
unknown (not predefined) attributed asked for. It is also callable, returning (of course) a turtle.

After a turtle is used, it can be inspected to find out what happened:

  >>> leonardo = Turtle()
  >>> leonardo.color = "blue"
  >>> leonardo.attack(weapon="katanas") #doctest:+ELLIPSIS
  <testify.utils.turtle.Turtle object at 0x...>

  >>> len(leonardo.defend)
  0

  >>> len(leonardo.attack)
  1

  >>> leonardo.attack.calls
  [((), {'weapon': 'katanas'})]

  >>> for args, kwargs in leonardo.attack:
  ...     print(kwargs.get('weapon'))
  katanas

To control the behavior of a turtle (for example, if you want some function call to return False instead)
just set the attribute yourself

  >>> raphael = Turtle(color="red")
  >>> raphael.is_shell_shocked = lambda : False

Then you can call:
  >>> if not raphael.is_shell_shocked():
  ...     print(raphael.color)
  red

"Turtles all the way down": http://en.wikipedia.org/wiki/Turtles_all_the_way_down
"""


class Turtle(object):
    def __init__(self, *args, **kwargs):
        self.__dict__.update(kwargs)

        self.calls = []
        self.returns = []

    def __iter__(self):
        return iter(self.calls)

    def __len__(self):
        return len(self.calls)

    def __nonzero__(self):
        return True

    def __bool__(self):
        return True

    def __getattr__(self, name):
        self.__dict__[name] = Turtle()
        return self.__dict__[name]

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        new_turtle = type(self)()
        self.returns.append(new_turtle)
        return new_turtle
