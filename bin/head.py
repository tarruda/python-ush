# test stub to generate bytes as input for other tests. This is equivalent to:
# $ while true; do echo -n "0123456789abcdef"; done | head -c COUNT
import argparse
import sys


def parse_argv():
    parser = argparse.ArgumentParser('output first COUNT input bytes')
    parser.add_argument('-c', '--count', type=int, required=True)
    return parser.parse_args()


def main():
    args = parse_argv()
    remaining = args.count
    while remaining:
        chunk = sys.stdin.read(1024)
        if not chunk:
            break
        output = chunk[:remaining] if remaining < len(chunk) else chunk
        remaining -= len(output)
        sys.stdout.write(output)


if __name__ == '__main__':
    main()
