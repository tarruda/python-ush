import os

import pytest

from helper import pwd, s, sh


@pytest.fixture()
def dirs(tmpdir):
    gp = tmpdir.mkdir('gp')
    p1 = gp.mkdir('p1')
    c1 = p1.mkdir('c1')
    c2 = p1.mkdir('c2')
    p2 = gp.mkdir('p2')
    l = [gp, p1, c1, c2, p2]
    return [os.path.dirname(str(gp))] + [os.path.basename(str(d)) for d in l]


def test_chdir(dirs):
    base, gp, p1, c1, c2, p2 = dirs
    with sh.chdir(base):
        assert list(pwd)[0] == base
        with sh.chdir(gp):
            assert list(pwd)[0] == os.path.join(base, gp)
            with sh.chdir(p1):
                assert list(pwd)[0] == os.path.join(base, gp, p1)
                with sh.chdir(c1):
                    assert list(pwd)[0] == os.path.join(base, gp, p1, c1)
                with sh.chdir(c2):
                    assert list(pwd)[0] == os.path.join(base, gp, p1, c2)
                assert list(pwd)[0] == os.path.join(base, gp, p1)
            with sh.chdir(p2):
                assert list(pwd)[0] == os.path.join(base, gp, p2)
        assert list(pwd)[0] == base
