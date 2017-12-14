import hashlib
import os

import pytest
from six import BytesIO, StringIO, PY2

from helper import *


repeat_hex = repeat('-c', '100', '0123456789abcdef')


def s(s):
    """Helper to normalize linefeeds."""
    if isinstance(s, bytes):
        return s.replace(b'\n', os.linesep.encode())
    else:
        return s.replace('\n', os.linesep)


def test_simple_success():
    assert cat('.textfile')() == (0,)


def test_simple_failure():
    assert cat('inexistent-file')() != (0,)


def test_redirect_stdout():
    sink = BytesIO()
    assert (cat('.textfile') | sink)() == (0,)
    assert sink.getvalue() == s(b'123\n1234\n12345\n')


def test_redirect_stdin():
    source = BytesIO()
    source.write(s(b'abc\ndef'))
    assert (source | cat)() == (0,)


def test_redirect_stdout_and_stdin():
    source = BytesIO()
    source.write(s(b'abc\ndef'))
    source.seek(0)
    sink = BytesIO()
    assert (source | cat | sink)() == (0,)
    assert sink.getvalue() == source.getvalue()


def test_one_pipe():
    sink = BytesIO()
    assert (repeat_hex | sha256sum | sink)() == (0, 0,)
    assert (
        sink.getvalue() ==
        s(b'1f1a5c83e53c9faa87badd5d17c45ffec'
          b'49b137430c9817dd5c9420fd96aaa3e\n'))


def test_two_pipes():
    sink = BytesIO()
    assert (repeat_hex | sha256sum | fold('-w', 16) | sink)() == (0, 0, 0,)
    assert (
        sink.getvalue() ==
        s(b'1f1a5c83e53c9faa\n'
          b'87badd5d17c45ffe\n'
          b'c49b137430c9817d\n'
          b'd5c9420fd96aaa3e\n'))


def test_three_pipes():
    sink = BytesIO()
    assert (repeat_hex | sha256sum | fold('-w', 16) | head('-c', 18) |
            sink)() == (0, 0, 0, 0,)
    assert sink.getvalue() == s(b'1f1a5c83e53c9faa\n8')


def test_stderr_redirect():
    stderr_sink = BytesIO()
    sink = BytesIO()
    source = BytesIO()
    source.write(b'123\n')
    source.seek(0)
    assert (source | errmd5 >> stderr_sink | errmd5 >> stderr_sink |
            sink)() == (0, 0)
    assert stderr_sink.getvalue() == (
        s(b'ba1f2511fc30423bdbb183fe33f3dd0f\n') * 2)
    assert sink.getvalue() == s(b'123\n')


def test_stderr_redirect_to_stdout():
    sink = BytesIO()
    source = BytesIO()
    source.write(s(b'123\n'))
    source.seek(0)
    assert (source | errmd5 >> STDOUT | errmd5 | sink)() == (0, 0)
    assert sink.getvalue() == s(b'123\n'
                                b'ba1f2511fc30423bdbb183fe33f3dd0f\n')
    source.seek(0)
    sink.seek(0)
    assert (source | errmd5 >> STDOUT | errmd5 >> STDOUT | sink)() == (0, 0)
    assert sink.getvalue() == s(b'123\n'
                                b'ba1f2511fc30423bdbb183fe33f3dd0f\n'
                                b'ba5d6480bba42f55a708ac7096374f7a\n')


def test_string_input_output():
    assert str(repeat('-c', '5', '123')) == '123123123123123'
    assert bytes(repeat('-c', '5', '123')) == b'123123123123123'
    if PY2:
        assert unicode(repeat('-c', '5', '123')) == u'123123123123123'
    assert str(StringIO(s('abc\ndef')) | cat) == s('abc\ndef')
    assert bytes(StringIO(s('abc\ndef')) | cat) == s(b'abc\ndef')
    if PY2:
        assert unicode(StringIO(s('abc\ndef')) | cat) == s(u'abc\ndef')


def test_stdin_redirect_file():
    assert str('.textfile' | cat) == s('123\n1234\n12345\n')


def test_stdout_stderr_redirect_file():
    (StringIO('hello') | errmd5 >> '.stderr' | '.stdout')()
    with open('.stdout', 'rb') as f:
        assert f.read() == b'hello'
    with open('.stderr', 'rb') as f:
        assert f.read() == s(b'5d41402abc4b2a76b9719d911017c592\n')
    (StringIO(s('\nworld\n')) | errmd5 >> '.stderr+' | '.stdout+')()
    with open('.stdout', 'rb') as f:
        assert f.read() == s(b'hello\nworld\n')
    with open('.stderr', 'rb') as f:
        assert f.read() == s(b'5d41402abc4b2a76b9719d911017c592\n'
                             b'81f82f69f5be2752005dae73e0f22f76\n')


def test_iterator_input():
    assert str((n for n in [1, 2, 3, 4]) | cat) == '1234'
    assert str(['ab', 2, s('\n'), 5] | cat) == s('ab2\n5')


def test_iterator_output():
    chunks = []
    for chunk in repeat('-c', '5', '123'):
        chunks.append(chunk)
    assert chunks == ['123123123123123']
    chunks = []
    for chunk in BytesIO(s(b'123\n')) | errmd5 >> STDOUT | errmd5 >> STDOUT:
        chunks.append(chunk)
    assert chunks == [
        '123',
        'ba1f2511fc30423bdbb183fe33f3dd0f',
        'ba5d6480bba42f55a708ac7096374f7a',
    ]


def test_iterator_output_multiple_pipes():
    chunks = []
    for chunk in BytesIO(s(b'123\n')) | errmd5 >> PIPE | errmd5 >> PIPE:
        chunks.append(chunk)
    assert len(chunks) == 3
    assert (s('ba1f2511fc30423bdbb183fe33f3dd0f'), None, None) in chunks
    assert (None, s('ba1f2511fc30423bdbb183fe33f3dd0f'), None) in chunks
    assert (None, None, s('123')) in chunks


@pytest.mark.parametrize('chunk_factor', [16, 32, 64, 128, 256])
def test_big_data(chunk_factor):
    def generator():
        b = (
            b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
            * chunk_factor
        )
        sent = 0
        total = 32 * 1024 * 1024
        while sent < total:
            yield b
            sent += len(b)
    md5 = hashlib.md5()
    stderr_1 = None
    stderr_2 = None
    chunk_count = 0
    for err1, err2, chunk in (
      generator() | errmd5 >> PIPE | errmd5 >> PIPE).iter_raw():
        chunk_count += 1
        if err1 is not None:
            assert stderr_1 is None
            stderr_1 = err1
        elif err2 is not None:
            assert stderr_2 is None
            stderr_2 = err2
        else:
            md5.update(chunk)
    assert stderr_1 == s(b'80365aea26be3a31ce7f953d7b01ea0d\n')
    assert stderr_2 == s(b'80365aea26be3a31ce7f953d7b01ea0d\n')
    assert md5.hexdigest() == '80365aea26be3a31ce7f953d7b01ea0d'
