import hashlib
import sys


def main():
    m = hashlib.sha256()
    while True:
        chunk = sys.stdin.read(1024)
        if not chunk:
            break
        m.update(chunk)
    sys.stdout.write(m.hexdigest() + '\n')


if __name__ == '__main__':
    main()
