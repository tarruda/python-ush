import os
import sys
import ush

__all__ = ('cat', 'env', 'fold', 'head', 'repeat', 'sha256sum', 'errmd5',
           'STDOUT', 'PIPE', 's')

SOURCE_ROOT = os.path.join(os.path.abspath(os.path.dirname(__file__)))
TEST_BIN_DIR = os.path.join(SOURCE_ROOT, 'bin')

sh = ush.Shell()


def commands(*names):
    argvs = []
    for name in names:
        script = os.path.join(TEST_BIN_DIR, '{0}.py'.format(name))
        argvs.append([sys.executable, script])
    return sh(*argvs)


def s(s):
    """Helper to normalize linefeeds."""
    if isinstance(s, bytes):
        return s.replace(b'\n', os.linesep.encode())
    else:
        return s.replace('\n', os.linesep)


cat, env, fold, head, repeat, sha256sum, errmd5 = commands(
    'cat', 'env', 'fold', 'head', 'repeat', 'sha256sum', 'errmd5')
STDOUT = ush.STDOUT
PIPE = ush.PIPE
