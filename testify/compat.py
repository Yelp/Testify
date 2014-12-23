PY2 = str is bytes
PY3 = str is not bytes

# flake8: noqa

if PY2:  # pragma: no cover PY2
    import __builtin__ as builtins
else:  # pragma: no cover PY3
    import builtins
