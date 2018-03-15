import os
import sys
import ush

__all__ = ('cat', 'env', 'fold', 'head', 'repeat', 'sha256sum', 'errmd5',
           'pargs', 'pwd', 'STDOUT', 'PIPE', 's', 'sh')

SOURCE_ROOT = os.path.join(os.path.abspath(os.path.dirname(__file__)))
TEST_BIN_DIR = os.path.join(SOURCE_ROOT, 'bin')

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


ush.Shell().export_as_module('sh', full_name=True)
import sh
for name in ['cat', 'env', 'fold', 'head', 'repeat', 'sha256sum', 'errmd5',
             'pargs', 'pwd']:
    script = os.path.join(TEST_BIN_DIR, '{0}.py'.format(name))
    alias_dict = {name: [sys.executable, script]}
    sh.alias(**alias_dict)
from sh import cat, env, fold, head, repeat, sha256sum, errmd5, pargs, pwd

STDOUT = ush.STDOUT
PIPE = ush.PIPE
