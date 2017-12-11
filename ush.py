import collections
import os
import subprocess
import sys


STDOUT = subprocess.STDOUT
PIPE = subprocess.PIPE
DEVNULL = object()
MAX_CHUNK_SIZE = 0xffff

# We have python2/3 compatibility, but don't want to rely on `six` package so
# this script can be used independently.
try:
    xrange
    from Queue import Queue, Empty
    import StringIO
    BytesIO = StringIO.StringIO
    def is_string(o):
        return isinstance(o, basestring)
    to_cstr = str
    PY3 = False
except NameError:
    xrange = range
    from queue import Queue, Empty
    import io
    BytesIO = io.BytesIO
    def is_string(o):
        return isinstance(o, str) or isinstance(o, bytes)
    def to_cstr(obj):
        if isinstance(obj, bytes):
            return obj
        return str(obj).encode('utf-8')
    PY3 = True


if sys.platform == 'win32':
    import threading
    def set_extra_popen_opts(opts):
        pass
    def concurrent_communicate(proc, read_streams):
        return concurrent_communicate_with_threads(proc, read_streams)
else:
    import select
    from signal import signal, SIGPIPE, SIG_DFL
    _PIPE_BUF = getattr(select, 'PIPE_BUF', 512)
    def set_extra_popen_opts(opts):
        # Restore SIGPIPE default handler when forked. This is required for
        # handling pipelines correctly.
        opts['preexec_fn'] = lambda: signal(SIGPIPE, SIG_DFL)
    def concurrent_communicate(proc, read_streams):
        return concurrent_communicate_with_select(proc, read_streams)


class InvalidPipeline(Exception):
    pass


class AlreadyRedirected(Exception):
    pass


class ProcessError(Exception):
    def __init__(self, process_info):
        super(ProcessError, self).__init__('One or more commands failed')
        self.process_info = process_info


def fileobj_has_fileno(fileobj):
    try:
        fileobj.fileno()
        return True
    except Exception:
        return False


def validate_pipeline(commands):
    for index, command in enumerate(commands):
        is_first = index == 0
        is_last = index == len(commands) - 1
        if not is_first and command.opts.get('stdin', None) is not None:
            msg = (
                'Command {0} is not the first in the pipeline and has '
                'stdin set to a value different than "None"'
            ).format(command)
            raise InvalidPipeline(msg)
        if not is_last and command.opts.get('stdout', None) is not None:
            msg = (
                'Command {0} is not the last in the pipeline and has '
                'stdout set to a value different than "None"'
            ).format(command)
            raise InvalidPipeline(msg)


def wait(procs, throw_on_error):
    status_codes = []
    result = tuple(iterate_outputs(procs, throw_on_error, status_codes))
    assert result == ()
    return tuple(status_codes)


def iterate_outputs(procs, throw_on_error, status_codes):
    read_streams = [proc.stderr_stream for proc in procs if proc.stderr]
    if procs[-1].stdout:
        read_streams.append(procs[-1].stdout_stream)
    write_stream = procs[0].stdin_stream if procs[0].stdin else None
    co = communicate(procs)
    wchunk = None
    while True:
        try:
            ri = co.send(wchunk)
            if ri:
                rchunk, i = ri
                if read_streams[i]:
                    read_streams[i].write(rchunk)
                else:
                    yield ri
        except StopIteration:
            break
        try:
            wchunk = next(write_stream) if write_stream else None
        except StopIteration:
            wchunk = None
    status_codes += [proc.wait() for proc in procs]
    if throw_on_error and len(list(filter(lambda c: c != 0, rv))):
        process_info = [
            (proc.args, proc.pid, proc.returncode) for proc in procs
        ]
        raise ProcessError(process_info)


def write_chunk(proc, chunk):
    try:
        proc.stdin.write(to_cstr(chunk))
    except IOError as e:
        if e.errno == errno.EPIPE:
            # communicate() should ignore broken pipe error
            pass
        elif (e.errno == errno.EINVAL and proc.poll() is not None):
            # Issue #19612: stdin.write() fails with EINVAL
            # if the process already exited before the write
            pass
        else:
            raise


def communicate(procs):
    # make a list of (readable streams, sinks) tuples
    read_streams = [proc.stderr for proc in procs if proc.stderr]
    if procs[-1].stdout:
        read_streams.append(procs[-1].stdout)
    writer = procs[0]
    if len(read_streams + [w for w in [writer] if w.stdin]) > 1:
        return concurrent_communicate(writer, read_streams)
    if writer.stdin or len(read_streams) == 1:
        return simple_communicate(writer, read_streams)
    else:
        return stub_communicate()


def stub_communicate():
    return
    yield


def simple_communicate(proc, read_streams):
    if proc.stdin:
        while True:
            chunk = yield
            if not chunk:
                break
            write_chunk(proc, chunk)
        proc.stdin.close()
    else:
        read_stream = read_streams[0]
        while True:
            chunk = read_stream.read(MAX_CHUNK_SIZE)
            if not chunk:
                break
            yield (chunk, 0)


def concurrent_communicate_with_select(proc, read_streams):
    reading = [] + read_streams
    writing = [proc.stdin] if proc.stdin else []
    indexes = dict((r.fileno(), i) for i, r in enumerate(read_streams))
    write_queue = collections.deque()

    while reading or writing:
        try:
            rlist, wlist, xlist = select.select(reading, writing, [])
        except select.error as e:
            if e.args[0] == errno.EINTR:
                continue
            raise

        for rstream in rlist:
            rchunk = os.read(rstream.fileno(), MAX_CHUNK_SIZE)
            if not rchunk:
                rstream.close()
                reading.remove(rstream)
                continue
            write_queue.append((yield rchunk, indexes[rstream.fileno()]))

        if not write_queue:
            write_queue.append((yield))

        if not wlist:
            continue

        while write_queue:
            wchunk = write_queue.popleft()
            if wchunk is None:
                assert not write_queue
                writing = []
                proc.stdin.close()
                break
            wchunk = to_cstr(wchunk)
            chunk = wchunk[:_PIPE_BUF]
            if len(wchunk) > _PIPE_BUF:
                write_queue.appendleft(wchunk[_PIPE_BUF:])
            try:
                written = os.write(proc.stdin.fileno(), chunk)
            except OSError as e:
                if e.errno != errno.EPIPE:
                    raise
                writing = []
                proc.stdin.close()
            else:
                if len(chunk) > written:
                    write_queue.appendleft(chunk[written:])
                    # break so we wait for the pipe buffer to be drained
                    break


def concurrent_communicate_with_threads(proc, read_streams):
    def read(queue, read_stream, index):
        while True:
            chunk = read_stream.read(MAX_CHUNK_SIZE)
            if not chunk:
                break
            queue.put((chunk, index))
        queue.put((None, index))

    def write(queue, proc):
        while True:
            chunk = queue.get()
            if not chunk:
                break
            write_chunk(proc, chunk)
        proc.stdin.close()

    rqueue = Queue(maxsize=1)
    wqueue = Queue()
    threads = []
    for i, rs in enumerate(read_streams):
        threads.append(threading.Thread(target=read, args=(rqueue, rs, i)))
        threads[-1].setDaemon(True)
        threads[-1].start()
    if proc.stdin:
        threads.append(threading.Thread(target=write, args=(wqueue, proc)))
        threads[-1].setDaemon(True)
        threads[-1].start()

    writing = True
    reading = len(read_streams)
    while writing or reading or rqueue.qsize():
        if reading or rqueue.qsize():
            try:
                rchunk, index = rqueue.get(block=not writing)
                if rchunk:
                    wchunk = yield rchunk, index
                else:
                    reading -= 1
                    continue
            except Empty:
                wchunk = yield
        else:
            wchunk = yield
        if writing:
            wqueue.put(wchunk)
            writing = wchunk is not None
    for t in threads:
        t.join()


def setup_redirect(proc_opts, key):
    close = False
    stream = proc_opts.get(key, None)
    if isinstance(stream, FileOpenWrapper):
        close = True
        stream = open(stream.path, stream.mode)
        proc_opts[key] = stream
    if stream in (None, STDOUT, PIPE) or fileobj_has_fileno(stream):
        # no changes required
        return None, close
    if key == 'stdin':
        if is_string(stream):
            stream = BytesIO(to_cstr(stream))
        if hasattr(stream, 'read'):
            # replace with an iterator that yields data in up to 64k chunks.
            # This is done to avoid the yield-by-line logic when iterating
            # file-like objects that contain binary data.
            stream = fileobj_to_iterator(stream)
        elif hasattr(stream, '__iter__'):
            stream = iter(stream)
    proc_opts[key] = PIPE
    return stream, close


def read(path):
    return FileOpenWrapper('rb', path)


def truncate(path):
    return FileOpenWrapper('wb', path)


def append(path):
    return FileOpenWrapper('ab', path)


def fileobj_to_iterator(fobj):
    def iterator():
        while True:
            data = fobj.read(MAX_CHUNK_SIZE)
            if not data:
                break
            yield data
    return iterator()


class FileOpenWrapper(object):
    def __init__(self, mode, path):
        self.mode = mode
        self.path = path


class RunningProcess(object):
    def __init__(self, popen, stdin_stream, stdout_stream, stderr_stream):
        self.popen = popen
        self.stdin_stream = stdin_stream
        self.stdout_stream = stdout_stream
        self.stderr_stream = stderr_stream

    @property
    def stdin(self):
        return self.popen.stdin

    @property
    def stdout(self):
        return self.popen.stdout

    @property
    def stderr(self):
        return self.popen.stderr

    @property
    def pid(self):
        return self.popen.pid

    def wait(self):
        return self.popen.wait()

    def poll(self):
        return self.popen.poll()


class Shell(object):
    def __init__(self, **defaults):
        self.defaults = defaults

    def command(self, *argv, **opts):
        command_opts = {}
        command_opts.update(self.defaults)
        command_opts.update(opts)
        return Command(argv, command_opts)


class PipelineBasePy3(object):
    def __bytes__(self):
        return self._collect_output()

    def __str__(self):
        return bytes(self).decode('utf-8')


class PipelineBasePy2(object):
    def __str__(self):
        return self._collect_output()

    def __unicode__(self):
        return str(self).decode('utf-8')


class Pipeline(PipelineBasePy3 if PY3 else PipelineBasePy2):
    def __init__(self, commands):
        validate_pipeline(commands)
        self.commands = commands

    def __repr__(self):
        return ' | '.join((repr(c) for c in self.commands))

    def __or__(self, other):
        if isinstance(other, Shell):
            return other(self)
        elif hasattr(other, 'write') or (
            isinstance(other, FileOpenWrapper) and other.mode in ['wb', 'ab']):
            # assume file-like obj
            return Pipeline(self.commands[:-1] +
                            [self.commands[-1]._redirect('stdout', other)])
        assert isinstance(other, Command)
        return Pipeline(self.commands + [other])

    def __ror__(self, other):
        if hasattr(other, '__iter__') or is_string(other) or (
            isinstance(other, FileOpenWrapper) and other.mode == 'rb'):
            return Pipeline([self.commands[0]._redirect('stdin', other)] +
                            self.commands[1:])
        assert False, "Invalid"

    def __call__(self):
        procs, throw_on_error = self._spawn()
        return wait(procs, throw_on_error)

    def __iter__(self):
        pipeline = Pipeline(self.commands[:-1] +
                            [self.commands[-1]._redirect('stdout', PIPE)])
        procs, throw_on_error = pipeline._spawn()
        pipe_count = sum(1 for proc in procs if proc.stderr)
        if procs[-1].stdout:
            pipe_count += 1
        if not pipe_count:
            wait(procs, throw_on_error)
            # nothing to yield
            return
        if pipe_count == 1:
            for rchunk, i in iterate_outputs(procs, throw_on_error, []):
                yield rchunk
        else:
            for rchunk, i in iterate_outputs(procs, throw_on_error, []):
                yield tuple(rchunk if i == index else None
                            for index in xrange(pipe_count))

    def _collect_output(self):
        sink = BytesIO()
        (self | sink)()
        return sink.getvalue()

    def _spawn(self):
        procs = []
        throw_on_error = False
        for index, command in enumerate(self.commands):
            close_in = False
            close_out = False
            close_err = False
            is_first = index == 0
            is_last = index == len(self.commands) - 1
            stdin_stream = None
            stdout_stream = None
            stderr_stream = None
            # copy argv/opts
            proc_argv = [str(a) for a in command.argv]
            proc_opts = command.opts.copy()
            throw_on_error = throw_on_error or proc_opts.get('throw_on_error',
                                                             False)
            if is_first:
                # first command in the pipeline may redirect stdin
                stdin_stream, close_in = setup_redirect(proc_opts, 'stdin')
            else:
                # only set current process stdin if it is not the first in the
                # pipeline.
                proc_opts['stdin'] = procs[-1].stdout
            if is_last:
                # last command in the pipeline may redirect stdout
                stdout_stream, close_out = setup_redirect(proc_opts, 'stdout')
            else:
                # only set current process stdout if it is not the last in the
                # pipeline.
                proc_opts['stdout'] = PIPE
            # stderr may be set at any point in the pipeline
            stderr_stream, close_err = setup_redirect(proc_opts, 'stderr')
            set_extra_popen_opts(proc_opts)
            current_proc = RunningProcess(
                subprocess.Popen(proc_argv, **proc_opts),
                stdin_stream, stdout_stream, stderr_stream
                )
            # if files were opened and connected to the process stdio, close
            # our copies of the descriptors
            if close_in:
                proc_opts['stdin'].close()
            if close_out:
                proc_opts['stdout'].close()
            if close_err:
                proc_opts['stderr'].close()
            if not is_first:
                # close our copy of the previous process's stdout, now that it
                # is connected to the current process's stdin
                procs[-1].stdout.close()
            procs.append(current_proc)
        return procs, throw_on_error


class Command(object):
    OPTS = ('stdin', 'stdout', 'stderr', 'env', 'cwd', 'throw_on_error')

    def __init__(self, argv, opts):
        self.argv = argv
        self.opts = {}
        for key in Command.OPTS:
            if key in opts:
                self.opts[key] = opts[key]

    def __call__(self, *argv, **opts):
        if not argv and not opts:
            # invoke the command
            return Pipeline([self])()
        new_opts = self.opts.copy()
        for key in Command.OPTS:
            if key in opts:
                new_opts[key] = opts[key]
        return Command(self.argv + argv, new_opts)

    def __repr__(self):
        argstr = ' '.join(self.argv)
        optstr = ' '.join(
            '{0}="{1}"'.format(key, getattr(self, key))
            for key in Command.OPTS if getattr(self, key, None) is not None
            )
        if optstr:
            return '{0} ({1})'.format(argstr, optstr)
        else:
            return argstr

    def __str__(self):
        return str(Pipeline([self]))

    def __bytes__(self):
        return bytes(Pipeline([self]))

    def __unicode__(self):
        return unicode(Pipeline([self]))

    def __iter__(self):
        return iter(Pipeline([self]))

    def __or__(self, other):
        return Pipeline([self]) | other

    def __ror__(self, other):
        return other | Pipeline([self])

    def __rshift__(self, other):
        return self._redirect('stderr', other)

    def _redirect(self, key, stream):
        if self.opts.get(key, None) is not None:
            raise AlreadyRedirected('command already redirects ' + key)
        return self(**{key: stream})
