import os
import sys
import ush

__all__ = ('cat', 'fold', 'head', 'repeat', 'sha256sum',)

SOURCE_ROOT = os.path.join(os.path.abspath(os.path.dirname(__file__)))
TEST_BIN_DIR = os.path.join(SOURCE_ROOT, 'bin')

def test_command(name):
    script = os.path.join(TEST_BIN_DIR, '{0}.py'.format(name))
    return bush.Command(sys.executable, script)

cat = test_command('cat')
fold = test_command('fold')
head = test_command('head')
repeat = test_command('repeat')
sha256sum = test_command('sha256sum')