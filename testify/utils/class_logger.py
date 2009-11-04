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
