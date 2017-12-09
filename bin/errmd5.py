import argparse
import hashlib
import shutil

import six

from compat import stdin, stdout, stderr


def parse_argv():
    parser = argparse.ArgumentParser(
        'copy stdin to stdout and output md5 to stderr')
    return parser.parse_args()


def main():
    args = parse_argv()
    out = six.BytesIO()
    shutil.copyfileobj(stdin, out)
    md5 = hashlib.md5()
    md5.update(out.getvalue())
    stdout.write(out.getvalue())
    stdout.flush()
    stderr.write(md5.hexdigest().encode() + b'\n')
    stderr.flush()


if __name__ == '__main__':
    main()
