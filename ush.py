import collections
import contextlib
import errno
import glob
import os
import re
import subprocess
import sys
import types


__all__ = ('Shell', 'Command', 'InvalidPipeline', 'AlreadyRedirected',
           'ProcessError')


STDOUT = subprocess.STDOUT
PIPE = subprocess.PIPE
NULL = object()
MAX_CHUNK_SIZE = 0xffff
GLOB_PATTERNS = re.compile(r'(?:\*|\?|\[[^\]]+\])')
GLOB_OPTS = {}

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
    if sys.version_info >= (3, 5):
        GLOB_OPTS = {'recursive': True}


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
        user_preexec_fn = opts.get('preexec_fn', None)
        def preexec_fn():
            if user_preexec_fn:
                user_preexec_fn()
            # Restore SIGPIPE default handler when forked. This is required for
            # handling pipelines correctly.
            signal(SIGPIPE, SIG_DFL)
        opts['preexec_fn'] = preexec_fn
    def concurrent_communicate(proc, read_streams):
        return concurrent_communicate_with_select(proc, read_streams)


class InvalidPipeline(Exception):
    pass


class AlreadyRedirected(Exception):
    pass


class ProcessError(Exception):
    def __init__(self, process_info):
        msg = 'One or more commands failed: {}'.format(process_info)
        super(ProcessError, self).__init__(msg)
        self.process_info = process_info


def expand_filenames(argv, cwd):
    def expand_arg(arg):
        return [os.path.relpath(p, cwd)
                for p in glob.iglob(os.path.join(cwd, arg), **GLOB_OPTS)]
    rv = [argv[0]]
    for arg in argv[1:]:
        if arg and arg[0] != '-' and GLOB_PATTERNS.search(arg):
            rv += expand_arg(arg)
        else:
            rv.append(arg)
    return rv


def update_opts_env(opts, extra_env):
    if extra_env is None:
        del opts['env']
        return
    env = opts.get('env', None)
    if env is None:
        env = {}
    else:
        env = env.copy()
    env.update(extra_env)
    opts['env'] = env


def set_environment(proc_opts):
    env = proc_opts.get('env', None)
    if env is None:
        return
    new_env = {}
    if proc_opts.get('merge_env', True):
        new_env.update(os.environ)
    new_env.update(env)
    # unset environment variables set to `None`
    for k in list(new_env.keys()):
        if new_env[k] is None: del new_env[k]
    proc_opts['env'] = new_env


def fileobj_has_fileno(fileobj):
    try:
        fileobj.fileno()
        return True
    except Exception:
        return False


def remove_invalid_opts(opts):
    new_opts = {}
    new_opts.update(opts)
    for opt in ('raise_on_error', 'merge_env', 'glob'):
        if opt in new_opts: del new_opts[opt] 
    return new_opts


LS = os.linesep
LS_LEN = len(LS)

def iterate_lines(chunk_iterator, trim_trailing_lf=False):
    remaining = {}
    for chunk, stream_id in chunk_iterator:
        chunk = remaining.get(stream_id, '') + chunk.decode('utf-8')
        last_ls_index = -LS_LEN
        while True:
            start = last_ls_index + LS_LEN
            try:
                ls_index = chunk.index(LS, start)
            except ValueError:
                remaining[stream_id] = chunk[last_ls_index + LS_LEN:]
                break
            yield chunk[start:ls_index], stream_id
            remaining[stream_id] = chunk[ls_index + LS_LEN:]
            last_ls_index = ls_index
    for stream_id in remaining:
        line = remaining[stream_id]
        if line or not trim_trailing_lf:
            yield line, stream_id


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


def wait(procs, raise_on_error):
    status_codes = []
    result = tuple(iterate_outputs(procs, raise_on_error, status_codes))
    assert result == ()
    return tuple(status_codes)


def iterate_outputs(procs, raise_on_error, status_codes):
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
    if raise_on_error and len(list(filter(lambda c: c != 0, status_codes))):
        process_info = [
            (proc.argv, proc.pid, proc.returncode) for proc in procs
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
    stream = proc_opts.get(key, None)
    if stream in (None, STDOUT, PIPE) or fileobj_has_fileno(stream):
        # Simple case which will be handled automatically by Popen: stream is
        # STDOUT/PIPE or a file object backed by file.
        return None, False
    if is_string(stream):
        # stream is a string representing a filename, we'll open the file with
        # appropriate mode which will be set to proc_opts[key].
        if key == 'stdin':
            proc_opts[key] = open(stream, 'rb')
        else:
            if stream.endswith('+'):
                proc_opts[key] = open(stream[:-1], 'ab')
                # On MS Windows we need to explicitly the file position to the
                # end or the file contents will be replaced.
                proc_opts[key].seek(0, os.SEEK_END)
            else:
                proc_opts[key] = open(stream, 'wb')
        return None, True
    if key == 'stdin':
        if hasattr(stream, 'read'):
            # replace with an iterator that yields data in up to 64k chunks.
            # This is done to avoid the yield-by-line logic when iterating
            # file-like objects that contain binary data.
            stream = fileobj_to_iterator(stream)
        elif hasattr(stream, '__iter__'):
            stream = iter(stream)
    proc_opts[key] = PIPE
    return stream, False


def fileobj_to_iterator(fobj):
    def iterator():
        while True:
            data = fobj.read(MAX_CHUNK_SIZE)
            if not data:
                break
            yield data
    return iterator()


class RunningProcess(object):
    def __init__(self, popen, stdin_stream, stdout_stream, stderr_stream,
                 argv):
        self.popen = popen
        self.stdin_stream = stdin_stream
        self.stdout_stream = stdout_stream
        self.stderr_stream = stderr_stream
        self.argv = argv

    @property
    def returncode(self):
        return self.popen.returncode

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
        self.aliases = {}
        self.envstack = []
        self.dirstack = []
        if 'env' in defaults:
            self.envstack.append(defaults['env'])
            del defaults['env']
        if 'cwd' in defaults:
            self.dirstack.append(defaults['cwd'])
            del defaults['cwd']
        self.defaults = defaults

    def __call__(self, *argvs, **opts):
        rv = []
        for argv in argvs:
            if is_string(argv):
                argv = self.aliases.get(argv, argv)
                if is_string(argv):
                    argv = [argv]
            rv.append(Command(argv, shell=self, **opts))
        return rv[0] if len(rv) == 1 else rv

    @contextlib.contextmanager
    def setenv(self, env):
        self.envstack.append(env)
        yield
        e = self.envstack.pop()
        assert e == env

    @contextlib.contextmanager
    def chdir(self, path):
        if path[0] != '/':
            # not absolute path, consider the current stack and join with the
            # last path
            if self.dirstack:
                path = os.path.normpath('{}/{}'.format(self.dirstack[-1],
                                                       path))
        self.dirstack.append(path)
        yield
        p = self.dirstack.pop()
        assert p == path

    def alias(self, **aliases):
        self.aliases.update(aliases)

    def export_as_module(self, module_name, full_name=False):
        if full_name:
            sys.modules[module_name] = ShellModule(self, module_name)
            return
        if module_name in globals():
            raise Exception('Name "{}" is already taken'.format(module_name))
        full_module_name = __name__ + '.' + module_name
        module = ShellModule(self, full_module_name)
        sys.modules[full_module_name] = module
        globals()[module_name] = module


class ShellModule(types.ModuleType):
    def __init__(self, shell, name):
        self.__shell = shell
        self.__file__ = '<frozen>'
        self.__name__ = name
        self.__package__ = __package__
        self.__loader__ = None

    def __repr__(self):
        return repr(self.__shell)

    def __getattr__(self, name):
        if name.startswith('__'):
            return super(ShellModule, self).__getattr__(name) 
        attr = getattr(self.__shell, name, None)
        if attr and name != 'export_as_module':
            return attr
        return self.__shell(name)


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
        elif hasattr(other, 'write') or is_string(other):
            return Pipeline(self.commands[:-1] +
                            [self.commands[-1]._redirect('stdout', other)])
        assert isinstance(other, Command)
        return Pipeline(self.commands + [other])

    def __ror__(self, other):
        if hasattr(other, '__iter__') or is_string(other):
            return Pipeline([self.commands[0]._redirect('stdin', other)] +
                            self.commands[1:])
        assert False, "Invalid"

    def __call__(self):
        procs, raise_on_error = self._spawn()
        return wait(procs, raise_on_error)

    def __iter__(self):
        return self._iter(False)

    def _iter(self, raw):
        pipeline = Pipeline(self.commands[:-1] +
                            [self.commands[-1]._redirect('stdout', PIPE)])
        procs, raise_on_error = pipeline._spawn()
        pipe_count = sum(1 for proc in procs if proc.stderr)
        if procs[-1].stdout:
            pipe_count += 1
        if not pipe_count:
            wait(procs, raise_on_error)
            # nothing to yield
            return
        iterator = iterate_outputs(procs, raise_on_error, [])
        if not raw:
            iterator = iterate_lines(iterator, trim_trailing_lf=True)
        if pipe_count == 1:
            for line, stream_index in iterator:
                yield line
        else:
            for line, stream_index in iterator:
                yield tuple(line if stream_index == index else None
                            for index in xrange(pipe_count))

    def _collect_output(self):
        sink = BytesIO()
        (self | sink)()
        return sink.getvalue()

    def _spawn(self):
        procs = []
        raise_on_error = False
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
            proc_opts = command.copy_opts()
            raise_on_error = raise_on_error or proc_opts.get('raise_on_error',
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
            if proc_opts.get('glob', False):
                proc_argv = expand_filenames(
                    proc_argv, os.path.realpath(
                        proc_opts.get('cwd', os.curdir)))
            set_environment(proc_opts)
            current_proc = RunningProcess(
                subprocess.Popen(proc_argv, **remove_invalid_opts(proc_opts)),
                stdin_stream, stdout_stream, stderr_stream, proc_argv
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
        return procs, raise_on_error

    def iter_raw(self):
        return self._iter(True)


class Command(object):
    OPTS = ('stdin', 'stdout', 'stderr', 'env', 'cwd', 'preexec_fn',
            'raise_on_error', 'merge_env', 'glob')

    def __init__(self, argv, shell=None, **opts):
        self.argv = tuple(argv)
        self.shell = shell
        self.opts = {}
        for key in opts:
            if key not in Command.OPTS:
                raise TypeError('Invalid keyword argument "{}"'.format(key))
            self.opts[key] = opts[key]

    def __call__(self, *argv, **opts):
        if not argv and not opts:
            # invoke the command
            return Pipeline([self])()
        new_opts = self.opts.copy()
        if 'env' in opts:
            update_opts_env(new_opts, opts['env'])
            del opts['env']
        for key in Command.OPTS:
            if key in opts:
                new_opts[key] = opts[key]
        return Command(self.argv + argv, shell=self.shell, **new_opts)

    def __repr__(self):
        argstr = ' '.join(self.argv)
        optstr = ' '.join(
            '{}={}'.format(key, self.get_opt(key))
            for key in self.iter_opts() if self.get_opt(key, None) is not None
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

    def _redirect(self, key, stream):
        if self.get_opt(key, None) is not None:
            raise AlreadyRedirected('command already redirects ' + key)
        return self(**{key: stream})

    def iter_raw(self):
        return Pipeline([self]).iter_raw()

    def get_env(self):
        if not self.shell.envstack and 'env' not in self.opts:
            return None
        env = {}
        for e in self.shell.envstack:
            env.update(e)
        env.update(self.opts.get('env', {}))
        return env

    def get_cwd(self):
        cwd = self.opts.get('cwd', None)
        if cwd:
            return cwd
        if self.shell.dirstack:
            return self.shell.dirstack[-1]
        return None

    def get_opt(self, opt, default=None):
        if opt == 'env':
            return self.get_env()
        if opt == 'cwd':
            return self.get_cwd()
        rv = self.opts.get(opt, NULL)
        if rv is NULL:
            rv = self.shell.defaults.get(opt, NULL)
        if rv is NULL:
            return default
        return rv

    def iter_opts(self):
        return set(list(self.opts.keys()) + list(self.shell.defaults.keys()) +
                   ['cwd', 'env'])

    def copy_opts(self):
        rv = {}
        for opt in self.iter_opts():
            val = self.get_opt(opt)
            if val is not None:
                rv[opt] = val
        return rv

builtin_sh = Shell(raise_on_error=True)
builtin_sh.alias(
    apt_cache='apt-cache',
    apt_get='apt-get',
    apt_key='apt-key',
    dpkg_divert='dpkg-divert',
    grub_install='grub-install',
    grub_mkconfig='grub-mkconfig',
    locale_gen='locale-gen',
    mkfs_ext2='mkfs.ext2',
    mkfs_ext3='mkfs.ext3',
    mkfs_ext4='mkfs.ext4',
    mkfs_vfat='mkfs.vfat',
    qemu_img='qemu-img',
    repo_add='repo-add',
    update_grub='update-grub',
    update_initramfs='update-initramfs',
    update_locale='update-locale',
    )
builtin_sh.export_as_module('sh')
