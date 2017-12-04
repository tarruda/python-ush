import hashlib


from compat import stdin, stdout


def main():
    m = hashlib.sha256()
    while True:
        chunk = stdin.read(1024)
        if not chunk:
            break
        m.update(chunk)
    stdout.write(m.hexdigest().encode() + b'\n')


if __name__ == '__main__':
    main()
