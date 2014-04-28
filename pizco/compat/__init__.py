# -*- coding: utf-8 -*-
"""
    pint.compat
    ~~~~~~~~~~~

    Compatibility layer.

    :copyright: 2013 by Pint Authors, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""

from __future__ import division, unicode_literals, print_function, absolute_import

import sys

PYTHON3 = sys.version >= '3'

if sys.version_info < (3, 2):
    import futures
else:
    from concurrent import futures

if sys.version_info < (2, 7):
    import unittest2 as unittest
else:
    import unittest

if PYTHON3:
    def u(x):
        return x

else:
    import codecs

    def u(x):
        return codecs.unicode_escape_decode(x)[0]

try:
    from logging import NullHandler
except ImportError:
    from .nullhandler import NullHandler

try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty

try:
    # location in Python 2.7 and 3.1
    from weakref import WeakSet
except ImportError:
    # separately installed
    from weakrefset import WeakSet
