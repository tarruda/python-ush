import sys
import bush

import six

from helper import *


sh = bush.Shell()


def test_simple_success():
    assert sh(cat('.textfile')) == (0,)


def test_simple_failure():
    assert sh(cat('inexistent-file')) != (0,)


def test_redirect_stdout():
    sink = six.BytesIO()
    assert sh(cat('.textfile') > sink) == (0,)
    assert sink.getvalue() == b'123\n1234\n12345\n'


def test_redirect_stdin():
    source = six.BytesIO()
    source.write(b'abc\ndef')
    assert sh(cat < source) == (0,)


def test_redirect_stdout_and_stdin():
    source = six.BytesIO()
    source.write(b'abc\ndef')
    sink = six.BytesIO()
    assert sh((cat < source) > sink) == (0,)
