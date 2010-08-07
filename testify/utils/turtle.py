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

  >>> leonardo = turtle.Turtle()
  >>> leonardo.color = "blue"
  >>> leonardo.attack(weapon="katanas")
  <testify.utils.turtle.Turtle object at 0x7fbd01e67dd0>

  >>> leonardo.do_katanas.calls
  [[((), {'weapon': katanas})]]

To control the behavior of a turtle (for example, if you want some function to call to return None instead)
just set the attribute yourself

  >>> raphael = Turtle()
  >>> raphael.color = "red"
  >>> raphael.is_lame = lambda : False

Then you can call:
  if raphael.color is None or raphael.is_lame():
      <do stuff>

"Turtles all the way down": http://en.wikipedia.org/wiki/Turtles_all_the_way_down
"""

class Turtle(object):
    def __init__(self, *args, **kwargs):
        self.__dict__.update(kwargs)
        self.calls = []

    def __getattr__(self, name):
        self.__dict__[name] = Turtle()
        return self.__dict__[name]
    
    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return Turtle()
