import pytest

from ush import iterate_lines


def chunk_iterator(data, chunk_size):
    while data:
        yield data[:chunk_size], 0
        data = data[chunk_size:]


DATA = b'Lorem \nipsum dolor \nsit amet\n'
@pytest.mark.parametrize('chunk_size', list(range(1, len(DATA))))
def test_iterate_lines(chunk_size):
    lines = [l for l, i in iterate_lines(chunk_iterator(DATA, chunk_size))]
    assert lines ==  ['Lorem ', 'ipsum dolor ', 'sit amet', '']

