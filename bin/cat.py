import argparse
import shutil
import sys


if sys.version_info[0] >= 3:
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
else:
    stdin = sys.stdin
    stdout = sys.stdout


def parse_argv():
    parser = argparse.ArgumentParser('concatenate files to stdout')
    parser.add_argument('files', type=argparse.FileType('rb'), nargs='*',
                                 default=[stdin])
    return parser.parse_args()


def main():
    args = parse_argv()
    for f in args.files:
        shutil.copyfileobj(f, stdout)
        f.close()


if __name__ == '__main__':
    main()
