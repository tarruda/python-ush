import hashlib
import shutil

import six

from compat import stdin, stdout, stderr


def main():
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
