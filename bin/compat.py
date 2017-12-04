import sys

if sys.version_info[0] >= 3:
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    stderr = sys.stderr.buffer
else:
    stdin = sys.stdin
    stdout = sys.stdout
    stderr = sys.stderr


