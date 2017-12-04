import argparse


from compat import stdin, stdout


def parse_argv():
    parser = argparse.ArgumentParser('wrap input lines of width of WIDTH')
    parser.add_argument('-w', '--width', type=int, required=True)
    return parser.parse_args()


def flush(buf):
    stdout.write(b''.join(buf + [b'\n']))


def main():
    args = parse_argv()
    width = args.width
    buf = []
    while True:
        c = stdin.read(1)
        if not c:
            break
        if c == b'\n':
            flush(buf)
            buf = []
            continue
        if len(buf) == width:
            flush(buf)
            buf = [c]
            continue
        buf.append(c)


if __name__ == '__main__':
    main()
