import argparse
import shutil
import sys


def parse_argv():
    parser = argparse.ArgumentParser('concatenate files to stdout')
    parser.add_argument('files', type=argparse.FileType('rb'), nargs='*',
                                 default=[sys.stdin])
    return parser.parse_args()


def main():
    args = parse_argv()
    for f in args.files:
        shutil.copyfileobj(f, sys.stdout)
        f.close()


if __name__ == '__main__':
    main()
