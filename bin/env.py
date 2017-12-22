# Helper to test environment variable inheritance. Prints only environment
# variables starting with USH_ 
import os

from compat import stdin, stdout


def main():
    for k in sorted(os.environ):
        if k.startswith('USH_'):
            print('{}={}'.format(k, os.environ[k]))


if __name__ == '__main__':
    main()
