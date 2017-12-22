import os
import sys

from helper import pargs, s


def norm_seps(paths):
    return [
        p.replace('/', os.path.sep) for p in paths
    ]


def test_glob_disabled_by_default():
    assert list(sorted(pargs('*.py'))) == ['*.py']


def test_glob():
    assert list(sorted(
        pargs('*.py', glob=True))) == [
        'helper.py', 'setup.py', 'ush.py'
    ]


def test_dont_expand_leading_dash():
    assert list(sorted(pargs('-*.py', glob=True))) == ['-*.py']


def test_glob_with_relative_dir():
    assert list(sorted(
        pargs('../*.py', cwd='bin', glob=True))) == norm_seps([
        '../helper.py', '../setup.py', '../ush.py'
    ])


if sys.version_info >= (3, 5):
    def test_glob_recursive():
        assert list(sorted(
            pargs('**/*.py', glob=True))) == norm_seps([
            'bin/__init__.py',
            'bin/cat.py',
            'bin/compat.py',
            'bin/env.py',
            'bin/errmd5.py',
            'bin/fold.py',
            'bin/head.py',
            'bin/pargs.py',
            'bin/repeat.py',
            'bin/sha256sum.py',
            'helper.py',
            'setup.py',
            'tests/__init__.py',
            'tests/test_commands.py',
            'tests/test_env.py',
            'tests/test_glob.py',
            'tests/test_util.py',
            'ush.py'
        ])


    def test_glob_recursive_with_relative_dir():
        assert list(sorted(
            pargs('../**/*.py', cwd='bin', glob=True))) == norm_seps([
            '../helper.py',
            '../setup.py',
            '../tests/__init__.py',
            '../tests/test_commands.py',
            '../tests/test_env.py',
            '../tests/test_glob.py',
            '../tests/test_util.py',
            '../ush.py',
            '__init__.py',
            'cat.py',
            'compat.py',
            'env.py',
            'errmd5.py',
            'fold.py',
            'head.py',
            'pargs.py',
            'repeat.py',
            'sha256sum.py'
        ])
