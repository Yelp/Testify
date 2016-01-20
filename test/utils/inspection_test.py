from testify import TestCase
from testify import setup
from testify import turtle
from testify.utils import inspection


class DummyTestCase(TestCase):

    @setup
    def fixture(self):
        pass

    turtle_method = turtle.Turtle()

    def instance(self):
        pass

    @staticmethod
    def static():
        pass


class IsFixtureMethodTest(TestCase):

    def test_fixture(self):
        assert inspection.is_fixture_method(DummyTestCase.fixture)

    def test_turtle(self):
        """Turtles are callable but not fixtures!"""
        assert not inspection.is_fixture_method(DummyTestCase.turtle_method)

    def test_lambda(self):
        assert not inspection.is_fixture_method(lambda: None)

    def test_static_method(self):
        assert not inspection.is_fixture_method(DummyTestCase.static)

    def test_instance(self):
        assert not inspection.is_fixture_method(DummyTestCase.instance)


class CallableSetattrTest(TestCase):

    def test_set_function_attr(self):
        def function():
            pass
        inspection.callable_setattr(function, 'foo', True)
        assert function.foo

    def test_set_method_attr(self):
        inspection.callable_setattr(DummyTestCase.fixture, 'foo', True)
        assert DummyTestCase.fixture.foo
