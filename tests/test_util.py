import os
import pytest

from ush import iterate_lines


def chunk_iterator(data, chunk_size):
    while data:
        yield data[:chunk_size], 0
        data = data[chunk_size:]


DATA = 'Lorem {0}ipsum dolor {0}sit amet{0}'.format(os.linesep).encode('utf-8')


@pytest.mark.parametrize('chunk_size', list(range(1, len(DATA))))
def test_iterate_lines(chunk_size):
    lines = [l for l, i in iterate_lines(chunk_iterator(DATA, chunk_size))]
    assert lines == ['Lorem ', 'ipsum dolor ', 'sit amet', '']

