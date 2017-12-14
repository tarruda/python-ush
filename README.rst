.. vim: ft=doctest
ush - Unix Shell
================

Python library that provides a convenient API/DSL for invoking and interacting
with external commands.

Basic Usage
-----------

>>> from ush import Shell
>>> sh = Shell()
>>> ls = sh.command('ls')

The `ls` variable is a `Command` object that wraps the `ls` external command:

>>> ls
ls

Calling the command without arguments will invoke the command and return the
exit code:

>>> ls()
(0,)

Command arguments can be added like this:

>>> ls('-l', '-a', '-h')
ls -l -a -h
>>> ls('-lah')()
(0,)

Adding arguments actually creates new `Command` instances with the appended
arguments. If the same arguments are used in future invocations, it can be
useful to save to a variable:

>>> ls = ls('--hide=__pycache__', '--hide=*.py*')

By default, standard input, output and error are inherited from the python
process. To capture output, simply call `str()` or `unicode()` on the `Command`
object:

>>> str(ls)
'bin\nLICENSE.txt\npytest.ini\nREADME.rst\nsetup.cfg\ntests\n'

The `Command` instances are also iterable, which is useful to process commands
that output a lot of data without consuming everything in memory. By default,
the iterator treats the command output as utf-8 and yields one item per line:

>>> files = []
>>> for line in ls:
...     files.append(line)
...
>>> files
[u'bin', u'LICENSE.txt', u'pytest.ini', u'README.rst', u'setup.cfg', u'tests']

It is possible to iterate on raw chunks of data (as received from the command)
by calling the `iter_raw()` method.

>>> list(ls.iter_raw())
[b'bin\nLICENSE.txt\npytest.ini\nREADME.rst\nsetup.cfg\ntests\n']

The normal behavior of invoking commands is return the exit code, even if it is
an error:

>>> ls('invalid-file')()
(2,)

If the command is passed `raise_on_error=True`, it will raise an exception if
the command returns non-zero codes: 

>>> ls('invalid-file', raise_on_error=True)()
Traceback (most recent call last):
...
ProcessError: One more commands failed

The directory and environment of the command can be customized with the `cwd`
and `env` options, respectively:

>>> import os
>>> new_env = {}
>>> new_env.update(os.environ)
>>> new_env['LS_COLORS'] = 'ExGxFxdxCxDxDxhbadExEx'
>>> ls(cwd='bin', env=new_env)()
(0,)

Pipelines
---------

Like with unix shells, it is possible to chain commands via the pipe (`|`)
operator:

>>> sort = sh.command('sort')('--reverse')
>>> ls | sort
ls --hide=__pycache__ --hide=*.py* | sort --reverse

Everything that can be done with single commands, can also be done with
pipelines:

>>> (ls | sort)()
(0, 0)
>>> str(ls | sort)
'tests\nsetup.cfg\nREADME.rst\npytest.ini\nLICENSE.txt\nbin\n'
>>> list(ls | sort)
[u'tests', u'setup.cfg', u'README.rst', u'pytest.ini', u'LICENSE.txt', u'bin']

Redirection
-----------

Redirecting stdin/stdout to files is also done with the `|` operator chained
with strings representing the filename:

>>> cat = sh.command('cat')
>>> echo = sh.command('echo')
>>> (ls | sort | '.stdout')()
(0, 0)
>>> str(cat('.stdout'))
'tests\nsetup.cfg\nREADME.rst\npytest.ini\nLICENSE.txt\nbin\n'
>>> str('setup.cfg' | cat)
'[metadata]\ndescription-file = README.rst\n'

In other words, a filename to the left side of the `|` will connect the file to
the command's stdin, a filename to the right side of the `|` will write the
command's stdout to the file.

When redirecting stdout, the file is truncated. To append to the file, add the
`+` suffix to the filename, For example:
>>> (echo('some more data') | cat | '.stdout+')()
(0, 0)
>>> str(cat('.stdout'))
'tests\nsetup.cfg\nREADME.rst\npytest.ini\nLICENSE.txt\nbin\nsome more data\n'

While only the first and last command of a pipeline may redirect stdin/stdout,
any command in a pipeline may redirect stderr through the `stderr` option: 
>>> ls('invalid-file', stderr='.stderr')()
(2,)
>>> str(cat('.stderr'))
"ls: cannot access 'invalid-file': No such file or directory\n"

Besides redirecting to/from filenames, it is possible to redirect to/from any
file-like object:

>>> from six import BytesIO
>>> sink = BytesIO()
>>> ls('invalid-file', stderr=sink)()
(2,)
>>> sink.getvalue()
b"ls: cannot access 'invalid-file': No such file or directory\n"
