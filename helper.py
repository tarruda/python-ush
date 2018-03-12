import os
import sys
import ush

__all__ = ('cat', 'env', 'fold', 'head', 'repeat', 'sha256sum', 'errmd5',
           'pargs', 'STDOUT', 'PIPE', 's', 'sh')

SOURCE_ROOT = os.path.join(os.path.abspath(os.path.dirname(__file__)))
TEST_BIN_DIR = os.path.join(SOURCE_ROOT, 'bin')

sh = ush.Shell()


def commands(*names):
    argvs = []
    for name in names:
        script = os.path.join(TEST_BIN_DIR, '{0}.py'.format(name))
        argvs.append([sys.executable, script])
    return sh(*argvs)


def s(obj):
    """Helper to normalize linefeeds in strings."""
    if isinstance(obj, bytes):
        return obj.replace(b'\n', os.linesep.encode())
    else:
        return obj.replace('\n', os.linesep)


cat, env, fold, head, repeat, sha256sum, errmd5, pargs = commands(
    'cat', 'env', 'fold', 'head', 'repeat', 'sha256sum', 'errmd5', 'pargs')
STDOUT = ush.STDOUT
PIPE = ush.PIPE
