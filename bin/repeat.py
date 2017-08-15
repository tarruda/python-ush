import argparse
import sys


if sys.version_info[0] > 2:
    range = xrange


def parse_argv():
    parser = argparse.ArgumentParser('repeat argument')
    parser.add_argument('data')
    parser.add_argument('-c', '--count', type=int, required=True)
    return parser.parse_args()


def main():
    args = parse_argv()
    data = args.data.encode('utf8')
    for _ in range(args.count):
        sys.stdout.write(data)


if __name__ == '__main__':
    main()
