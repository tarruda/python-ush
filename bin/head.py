import argparse

from compat import stdin, stdout


def parse_argv():
    parser = argparse.ArgumentParser('output first COUNT input bytes')
    parser.add_argument('-c', '--count', type=int, required=True)
    return parser.parse_args()


def main():
    args = parse_argv()
    remaining = args.count
    while remaining:
        chunk = stdin.read(1024)
        if not chunk:
            break
        output = chunk[:remaining] if remaining < len(chunk) else chunk
        remaining -= len(output)
        stdout.write(output)


if __name__ == '__main__':
    main()
