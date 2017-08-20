import subprocess
import sys
import threading


STDOUT = subprocess.STDOUT
PIPE = subprocess.PIPE
DEVNULL = object()


if sys.platform != 'win32':
    from signal import signal, SIGPIPE, SIG_DFL

    def set_extra_popen_opts(opts):
        # Restore SIGPIPE default handler when forked. This is required for
        # handling pipelines correctly.
        opts['preexec_fn'] = lambda: signal(SIGPIPE, SIG_DFL)

else:
    def set_extra_popen_opts(opts):
        pass


class InvalidPipeline(Exception):
    pass


class AlreadyRedirected(Exception):
    pass


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


class Base(object):
    def __repr__(self):
        return '<{0} "{1}">'.format(self.__class__.__name__, str(self))

    def __str__(self):
        return ''


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

    def communicate(self, stdindata=None):
        return self.popen.communicate(stdindata)

    def wait(self):
        return self.popen.wait()

    def stream_count(self):
        return len(filter(
            None, [self.stdin_stream, self.stdout_stream, self.stderr_stream]))


class Shell(Base):
    def __init__(self, throw_on_error=True):
        self.throw_on_error = throw_on_error

    def __call__(self, pipeline):
        if isinstance(pipeline, Command):
            pipeline = Pipeline([pipeline])
        return self._spawn_pipeline(pipeline)

    def _spawn_pipeline(self, pipeline):
        procs = []
        for index, command in enumerate(pipeline.commands):
            is_first = index == 0
            is_last = index == len(pipeline.commands) - 1
            stdin_stream = None
            stdout_stream = None
            stderr_stream = None
            # copy argv/opts
            proc_argv = command.argv[:]
            proc_opts = command.opts.copy()
            if is_first:
                # first command in the pipeline may redirect stdin
                stdin_stream = self._setup_redirect(proc_opts, 'stdin')
            else:
                # only set current process stdin if it is not the first in the
                # pipeline.
                proc_opts['stdin'] = procs[-1].stdout
            if is_last:
                # last command in the pipeline may redirect stdout
                stdout_stream = self._setup_redirect(proc_opts, 'stdout')
            else:
                # only set current process stdout if it is not the last in the
                # pipeline.
                proc_opts['stdout'] = PIPE
            # stderr may be set at any point in the pipeline
            stderr_stream = self._setup_redirect(proc_opts, 'stderr')
            set_extra_popen_opts(proc_opts)
            current_proc = RunningProcess(
                subprocess.Popen(proc_argv, **proc_opts),
                stdin_stream, stdout_stream, stderr_stream
                )
            if not is_first:
                # close our copy of the previous process's stdout, now that it
                # is connected to the current process's stdin
                procs[-1].stdout.close()
            procs.append(current_proc)
        return self._wait(procs)

    def _need_concurrent_wait(self, procs):
        rv = 0
        for proc in procs:
            rv += proc.stream_count()
        return rv > 1

    def _find_readable(self, procs):
        for proc in procs:
            if proc.stdout_stream:
                return proc.stdout, proc.stdout_stream
            elif proc.stderr_stream:
                return proc.stderr, proc.stderr_stream
        return None, None

    def _wait(self, procs):
        if self._need_concurrent_wait(procs):
            self._concurrent_wait(procs)
        else:
            self._simple_wait(procs)
        return tuple(proc.wait() for proc in procs)

    def _concurrent_wait(self, procs):
        # make a list of (readable streams, sinks) tuples
        readers = [(proc.stderr, proc.stderr_stream) for proc in procs
                   if proc.stderr_stream]
        if procs[-1].stdout_stream:
            readers.append((proc.stdout, proc.stdout_stream))
        self._concurrent_read_write(readers, procs[0].stdin,
                                    procs[0].stdin_stream)

    def _concurrent_read_write(self, readers, write_stream, source):
        threads = []
        for read_stream, sink in readers:
            threads.append(threading.Thread(
                target=lambda r, s: s.write(r.read()),
                args=(read_stream, sink)))
            threads[-1].setDaemon(True)
            threads[-1].start()
        if write_stream:
            try:
                write_stream.write(source.read())
            except IOError as e:
                if e.errno == errno.EPIPE:
                    # communicate() should ignore broken pipe error
                    pass
                elif (e.errno == errno.EINVAL and self.poll() is not None):
                    # Issue #19612: stdin.write() fails with EINVAL
                    # if the process already exited before the write
                    pass
                else:
                    raise
            write_stream.close()
        for t in threads:
            t.join()

    def _simple_wait(self, procs):
        if procs[0].stdin_stream:
            procs[0].communicate(procs[0].stdin_stream.read())
        else:
            for proc in procs:
                if proc.stdout_stream:
                    proc.stdout_stream.write(proc.communicate()[0])
                elif proc.stderr_stream:
                    proc.stderr_stream.write(proc.communicate()[1])
                else:
                    continue
                break

    def _setup_redirect(self, proc_opts, key):
        stream = proc_opts.get(key, None)
        if stream is None or hasattr(stream, 'fileno'):
            # no changes required
            return
        proc_opts[key] = PIPE
        return stream


class Pipeline(Base):
    def __init__(self, commands):
        validate_pipeline(commands)
        self.commands = commands

    def __str__(self):
        return ' | '.join((str(c) for c in self.commands))

    def __or__(self, command):
        return Pipeline(self.commands + [command])

    def __lt__(self, stdin):
        return Pipeline([self.commands[0] < stdin] + self.commands[1:])

    def __gt__(self, stdout):
        return Pipeline(self.commands[:-1] + [self.commands[-1] > stdout])

    def __ge__(self, stderr):
        return Pipeline(self.commands[:-1] + [self.commands[-1] >= stderr])


class Command(Base):
    OPTS = ('stdin', 'stdout', 'stderr', 'env', 'cwd',)

    def __init__(self, *argv, **opts):
        self.argv = argv
        self.opts = {}
        for key in Command.OPTS:
            if key in opts:
                self.opts[key] = opts[key]

    def __call__(self, *argv, **opts):
        new_opts = self.opts.copy()
        for key in Command.OPTS:
            if key in opts:
                new_opts[key] = opts[key]
        return Command(*(self.argv + argv), **new_opts)

    def __str__(self):
        argstr = ' '.join(self.argv)
        optstr = ' '.join(
            '{0}="{1}"'.format(key, getattr(self, key))
            for key in Command.OPTS if getattr(self, key, None) is not None
            )
        if optstr:
            return '{0} ({1})'.format(argstr, optstr)
        else:
            return argstr

    def __or__(self, other):
        return Pipeline([self, other])

    def __lt__(self, stream):
        return self._redirect('stdin', stream)

    def __gt__(self, stream):
        return self._redirect('stdout', stream)

    def __ge__(self, stream):
        return self._redirect('stderr', stream)

    def _redirect(self, key, stream):
        if self.opts.get(key, None) is not None:
            raise AlreadyRedirected('command already redirects ' + key)
        return self(**{key: stream})
