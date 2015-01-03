from __future__ import absolute_import

import io

import six


if six.PY2:
    NativeIO = io.BytesIO
else:
    NativeIO = io.StringIO
