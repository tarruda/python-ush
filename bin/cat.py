import argparse
import shutil

from compat import stdin, stdout


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
