import sys

import six

from helper import *
from ush import read, truncate, append


repeat_hex = repeat('-c', '100', '0123456789abcdef')


def test_simple_success():
    assert cat('.textfile')() == (0,)


def test_simple_failure():
    assert cat('inexistent-file')() != (0,)


def test_redirect_stdout():
    sink = six.BytesIO()
    assert (cat('.textfile') | sink)() == (0,)
    assert sink.getvalue() == b'123\n1234\n12345\n'


def test_redirect_stdin():
    source = six.BytesIO()
    source.write(b'abc\ndef')
    assert (source | cat)() == (0,)


def test_redirect_stdout_and_stdin():
    source = six.BytesIO()
    source.write(b'abc\ndef')
    source.seek(0)
    sink = six.BytesIO()
    assert (source | cat | sink)() == (0,)
    assert sink.getvalue() == source.getvalue()


def test_one_pipe():
    sink = six.BytesIO()
    assert (repeat_hex | sha256sum | sink)() == (0, 0,)
    assert (
        sink.getvalue() ==
        b'1f1a5c83e53c9faa87badd5d17c45ffec49b137430c9817dd5c9420fd96aaa3e\n')


def test_two_pipes():
    sink = six.BytesIO()
    assert (repeat_hex | sha256sum | fold('-w', 16) | sink)() == (0, 0, 0,)
    assert (
        sink.getvalue() ==
        (b'1f1a5c83e53c9faa\n'
         b'87badd5d17c45ffe\n'
         b'c49b137430c9817d\n'
         b'd5c9420fd96aaa3e\n'))


def test_three_pipes():
    sink = six.BytesIO()
    assert (repeat_hex | sha256sum | fold('-w', 16) | head('-c', 18) |
            sink)() == (0, 0, 0, 0,)
    assert sink.getvalue() == b'1f1a5c83e53c9faa\n8'


def test_stderr_redirect():
    stderr_sink = six.BytesIO()
    sink = six.BytesIO()
    source = six.BytesIO()
    source.write(b'123\n')
    source.seek(0)
    assert (source | errmd5 >> stderr_sink | errmd5 >> stderr_sink |
            sink)() == (0, 0)
    assert stderr_sink.getvalue() == b'ba1f2511fc30423bdbb183fe33f3dd0f\n' * 2
    assert sink.getvalue() == b'123\n'


def test_stderr_redirect_to_stdout():
    sink = six.BytesIO()
    source = six.BytesIO()
    source.write(b'123\n')
    source.seek(0)
    assert (source | errmd5 >> STDOUT | errmd5 | sink)() == (0, 0)
    assert sink.getvalue() == (b'123\n'
                               b'ba1f2511fc30423bdbb183fe33f3dd0f\n')
    source.seek(0)
    sink.seek(0)
    assert (source | errmd5 >> STDOUT | errmd5 >> STDOUT | sink)() == (0, 0)
    assert sink.getvalue() == (b'123\n'
                               b'ba1f2511fc30423bdbb183fe33f3dd0f\n'
                               b'ba5d6480bba42f55a708ac7096374f7a\n')



def test_string_input_output():
    assert str('abc\ndef' | cat) == 'abc\ndef'
    assert bytes('abc\ndef' | cat) == b'abc\ndef'
    if six.PY2:
        assert unicode('abc\ndef' | cat) == u'abc\ndef'


def test_stdin_redirect_file():
    assert str(read('.textfile') | cat) == '123\n1234\n12345\n'


def test_stdout_stderr_redirect_file():
    ('hello' | errmd5 >> truncate('.stderr') | truncate('.stdout'))()
    with open('.stdout', 'rb') as f:
        assert f.read() == b'hello'
    with open('.stderr', 'rb') as f:
        assert f.read() == b'5d41402abc4b2a76b9719d911017c592\n'
    ('\nworld\n' | errmd5 >> append('.stderr') | append('.stdout'))()
    with open('.stdout', 'rb') as f:
        assert f.read() == b'hello\nworld\n'
    with open('.stderr', 'rb') as f:
        assert f.read() == (b'5d41402abc4b2a76b9719d911017c592\n'
                            b'81f82f69f5be2752005dae73e0f22f76\n')


def test_iterator_input():
    assert str((n for n in [1, 2, 3, 4]) | cat) == '1234'
    assert str(['ab', 2, '\n', 5] | cat) == 'ab2\n5'


def test_iterator_output():
    chunks = []
    for chunk in b'123\n' | errmd5 >> STDOUT | errmd5 >> STDOUT:
        chunks.append(chunk)
    assert b''.join(chunks) == (b'123\n'
                                b'ba1f2511fc30423bdbb183fe33f3dd0f\n'
                                b'ba5d6480bba42f55a708ac7096374f7a\n')
