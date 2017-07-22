import subprocess
import sys


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


def validate_pipeline(commands):
    for index, command in enumerate(commands):
        is_first = index == 0
        is_last = index == len(commands) - 1
        if not is_first and command.opts.get('stdin', None) in [PIPE, DEVNULL]:
            msg = (
                'Command {0} is not the first in the pipeline and has '
                'stdin set to a value different than "None"'
            ).format(command)
            raise InvalidPipeline(msg)
        if not is_last and command.opts.get('stdout', None) in [PIPE, DEVNULL]:
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


class Shell(Base):
    def __init__(self, throw_on_error=True):
        self.throw_on_error = throw_on_error

    def __call__(self, pipeline):
        procs = []
        for index, command in enumerate(pipeline.commands):
            is_first = index == 0
            is_last = index == len(pipeline.commands) - 1
            # copy argv/opts
            proc_argv = command.argv[:]
            proc_opts = command.opts.copy()
            if not is_first:
                # only set current process stdin if it is not the first in the
                # pipeline.
                proc_opts['stdin'] = procs[-1].stdout
            if not is_last:
                # only set current process stdout if it is not the last in the
                # pipeline.
                proc_opts['stdout'] = PIPE
            set_extra_popen_opts(proc_opts)
            current_proc = subprocess.Popen(proc_argv, **proc_opts)
            if not is_first:
                # close our copy of the previous process's stdout, now that it
                # is connected to the current process's stdin
                procs[-1].stdout.close()
            procs.append(current_proc)
        return [proc.wait() for proc in procs]


class Pipeline(Base):
    def __init__(self, commands):
        self.commands = commands

    def __str__(self):
        return ' | '.join((str(c) for c in self.commands))

    def __or__(self, other):
        new_commands = self.commands + other.commands
        validate_pipeline(new_commands)
        return Pipeline(new_commands)


class Command(Pipeline):
    OPTS = ('stdin', 'stdout', 'stderr', 'env', 'cwd',)

    def __init__(self, *argv, **opts):
        self.argv = argv
        self.opts = {}
        for key in Command.OPTS:
            if key in opts:
                self.opts[key] = opts[key]
        super(Command, self).__init__([self])

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
