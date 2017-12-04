import sys
import bush

import six

from helper import *


sh = bush.Shell()

repeat_hex = repeat('-c', '100', '0123456789abcdef')


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
    source.seek(0)
    sink = six.BytesIO()
    assert sh((cat < source) > sink) == (0,)
    assert sink.getvalue() == source.getvalue()


def test_one_pipe():
    sink = six.BytesIO()
    assert sh(repeat_hex | sha256sum > sink) == (0, 0,)
    assert (
        sink.getvalue() ==
        b'1f1a5c83e53c9faa87badd5d17c45ffec49b137430c9817dd5c9420fd96aaa3e\n')


def test_two_pipes():
    sink = six.BytesIO()
    assert sh(repeat_hex | sha256sum | fold('-w', 16) > sink) == (0, 0, 0,)
    assert (
        sink.getvalue() ==
        (b'1f1a5c83e53c9faa\n'
         b'87badd5d17c45ffe\n'
         b'c49b137430c9817d\n'
         b'd5c9420fd96aaa3e\n'))


def test_three_pipes():
    sink = six.BytesIO()
    assert sh(repeat_hex | sha256sum | fold('-w', 16) | head('-c', 18) >
              sink) == (0, 0, 0, 0,)
    assert (sink.getvalue() == b'1f1a5c83e53c9faa\n8')
