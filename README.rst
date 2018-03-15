.. vim: ft=doctest
ush - Unix Shell
================

.. image:: https://circleci.com/gh/tarruda/python-ush.svg?style=svg
    :target: https://circleci.com/gh/tarruda/python-ush

.. image:: https://ci.appveyor.com/api/projects/status/p5n9fy83nx4ac24b?svg=true
    :target: https://ci.appveyor.com/project/tarruda/python-ush

Python library that provides a convenient but powerful API for invoking external
commands. Features:

- Idiomatic API for invoking commands
- Command chaining with `|`
- Redirection
- Windows/Unix support
- Python2/3 support
- Filename argument expansion (globbing)

Installation
------------

.. code-block::

  pip install ush


Basic Usage
-----------

>>> import os; os.environ['LANG'] = 'C.UTF-8'
>>> from ush import Shell
>>> sh = Shell()
>>> ls = sh('ls')

The ``ls`` variable is a ``Command`` object that wraps the ``ls`` external command:

>>> ls
ls

Calling the command without arguments will invoke the command and return the
exit code:

>>> ls()
(0,)

This is how arguments can be added:

>>> ls('-l', '-a', '-h')
ls -l -a -h
>>> ls('-lah')()
(0,)

Adding arguments actually creates new ``Command`` instances with the appended
arguments. If the same arguments are to be used in future invocations, it can be
useful to save to a variable:

>>> ls = ls('--hide=__pycache__', '--hide=*.py*', '--hide=*.yml', '--hide=*.txt', env={'LANG': 'C.UTF-8'})

By default, standard input, output and error are inherited from the python
process. To capture output, simply call `str()` or `unicode()` on the ``Command``
object:

>>> str(ls)
'README.rst\nbin\npytest.ini\nsetup.cfg\ntests\n'

``Command`` instances are also iterable, which is useful to process commands that
output a lot of data without consuming everything in memory. By default, the
iterator treats the command output as utf-8 and yields one item per line:

>>> files = []
>>> for line in ls:
...     files.append(line)
...
>>> files
[u'README.rst', u'bin', u'pytest.ini', u'setup.cfg', u'tests']

It is possible to iterate on raw chunks of data (as received from the command)
by calling the `iter_raw()` method.

>>> list(ls.iter_raw())
[b'README.rst\nbin\npytest.ini\nsetup.cfg\ntests\n']

The normal behavior of invoking commands is return the exit code, even if it is
an error:

>>> ls('invalid-file')()
(2,)

If the command is passed `raise_on_error=True`, it will raise an exception when
the external command returns non-zero codes: 

>>> ls('invalid-file', raise_on_error=True)()
Traceback (most recent call last):
...
ProcessError: One more commands failed

The directory and environment of the command can be customized with the ``cwd``
and ``env`` options, respectively:

>>> ls(cwd='bin', env={'LS_COLORS': 'ExGxFxdxCxDxDxhbadExEx'})()
(0,)

Default options
---------------

``Shell`` instances act like a factory for ``Command`` objects, and can be used to
hold default options for commands created by it:

>>> sh = Shell(raise_on_error=True)
>>> sort, cat, echo = sh(['sort', '--reverse'], 'cat', 'echo')
>>> sort
sort --reverse (raise_on_error=True)

It is possible to override when calling the ``Shell`` object:

>>> sort = sh(['sort', '--reverse'], cwd='bin', raise_on_error=None)
>>> sort
sort --reverse (cwd=bin)

>>> sort = sort(cwd=None)
>>> sort
sort --reverse

Pipelines
---------

Like with unix shells, it is possible to chain commands via the pipe (`|`)
operator:

>>> ls | sort
ls --hide=__pycache__ --hide=*.py* --hide=*.yml --hide=*.txt (env={'LANG': 'C.UTF-8'}) | sort --reverse

Everything that can be done with single commands, can also be done with
pipelines:

>>> (ls | sort)()
(0, 0)
>>> str(ls | sort)
'tests\nsetup.cfg\npytest.ini\nbin\nREADME.rst\n'
>>> list(ls | sort)
[u'tests', u'setup.cfg', u'pytest.ini', u'bin', u'README.rst']

Redirection
-----------

Redirecting stdin/stdout to files is also done with the `|` operator, but
chained with filenames instead of other ``Command`` instances:

>>> (ls | sort | '.stdout')()
(0, 0)
>>> str(cat('.stdout'))
'tests\nsetup.cfg\npytest.ini\nbin\nREADME.rst\n'
>>> str('setup.cfg' | cat)
'[metadata]\ndescription-file = README.rst\n\n[bdist_wheel]\nuniversal=1\n'

In other words, a filename on the left side of the `|` will connect the file to
the command's stdin, a filename on the right side of the `|` will write the
command's stdout to the file.

When redirecting stdout, the file is truncated by default. To append to the
file, add the `+` suffix to the filename, For example:

>>> (echo('some more data') | cat | '.stdout+')()
(0, 0)
>>> str(cat('.stdout'))
'tests\nsetup.cfg\npytest.ini\nbin\nREADME.rst\nsome more data\n'

While only the first and last command of a pipeline may redirect stdin/stdout,
any command in a pipeline may redirect stderr through the ``stderr`` option: 

>>> ls('invalid-file', stderr='.stderr', raise_on_error=False)()
(2,)
>>> str(cat('.stderr')) #doctest: +SKIP
"ls: cannot access 'invalid-file': No such file or directory\n"

Besides redirecting to/from filenames, it is possible to redirect to/from any
file-like object:

>>> from six import BytesIO
>>> sink = BytesIO()
>>> ls('invalid-file', stderr=sink, raise_on_error=False)()
(2,)
>>> sink.getvalue() #doctest: +SKIP
b"ls: cannot access 'invalid-file': No such file or directory\n"
>>> sink = BytesIO()
>>> (BytesIO(b'some in-memory data') | cat | sink)()
(0,)
>>> sink.getvalue()
b'some in-memory data'

To simplify passing strings to stdin of commands, the ``sh.echo`` helper is
provided:

>>> sink = BytesIO()
>>> (sh.echo('some in-memory data') | cat | sink)()
(0,)
>>> sink.getvalue()
b'some in-memory data'

>>> sink = BytesIO()
>>> (sh.echo(b'some in-memory data') | cat | sink)()
(0,)
>>> sink.getvalue()
b'some in-memory data'

``sh.echo`` is just a small wrapper around ``BytesIO`` or ``StringIO``.

Environment
-----------

Like with `subprocess.Popen`, environment variables are inherited by default,
but there are some differences with how the ``env`` option is handled:

1- The contents of the ``env`` option is merged with the current process's
environment by default:

>>> import os; os.environ['USH_TEST_VAR1'] = 'v1'
>>> env, grep = sh('env', 'grep', env={'USH_TEST_VAR2': 'v2'})
>>> list(sorted(env(env={'USH_TEST_VAR3': 'v3'}) | grep('^USH_TEST_')))
[u'USH_TEST_VAR1=v1', u'USH_TEST_VAR2=v2', u'USH_TEST_VAR3=v3']

2- To disable merging with the current process's environment (and adopt
`subprocess.Popen` behavior), pass `merge_env=False` with the ``env`` option.

>>> list(sorted(env(env={'USH_TEST_VAR3': 'v3'}, merge_env=False) | grep('^USH_TEST_')))
[u'USH_TEST_VAR2=v2', u'USH_TEST_VAR3=v3']

3- Variables can be cleared in the child process by passing a ``None`` value.

>>> list(sorted(env(env={'USH_TEST_VAR1': None}) | grep('^USH_TEST_')))
[u'USH_TEST_VAR2=v2']

As shown in the above examples, setting the ``env`` option always merges the
variables with previous invocations. To clear the value of the option, simply
pass ``None`` as the ``env`` option:

>>> env = env(env=None)
>>> list(sorted(env | grep('^USH_TEST_')))
[u'USH_TEST_VAR1=v1']
>>> env = env(env={'USH_TEST_VAR2': '2'})
>>> list(sorted(env | grep('^USH_TEST_')))
[u'USH_TEST_VAR1=v1', u'USH_TEST_VAR2=2']


Globbing
--------

Arguments passed to ``Command`` instances can be subject to filename
expansion. This feature is enabled with the ``glob`` option:

>>> echo = echo(glob=True)
>>> list(sorted(str(echo('*.py')).split()))
['helper.py', 'setup.py', 'ush.py']

To prevent messing with command switches, arguments starting with "-" are not
expanded:

>>> list(sorted(str(echo('-*.py')).split()))
['-*.py']

With Python 3.5+, this expansion can be recursive:

>>> list(sorted(str(echo('**/__init__.py')).split())) #doctest: +SKIP
['bin/__init__.py', 'tests/__init__.py']

Expansion is done relative to the command's ``cwd``:

>>> list(sorted(str(echo('**/__init__.py', cwd='bin')).split())) #doctest: +SKIP
['__init__.py']
>>> list(sorted(str(echo('../**/__init__.py', cwd='bin')).split())) #doctest: +SKIP
['../tests/__init__.py', '__init__.py']


Module syntax
-------------

It is possible to export ``Shell`` instances as modules, which enables a
convenient syntax for importing commands into the current namespace:

>>> sh.export_as_module('mysh')
>>> from ush.mysh import cat
>>> str('setup.cfg' | cat)
'[metadata]\ndescription-file = README.rst\n\n[bdist_wheel]\nuniversal=1\n'

By default, the module name passed to ``Shell.export_as_module`` is prefixed by
``ush.``. It is possible to specify the full module name like this:

>>> sh.export_as_module('mysh', full_name=True)
>>> from mysh import cat

Since only valid python identifiers can be imported with the module syntax, some
additional work is required to import commands which are not valid identifiers.
For example:

>>> sh.alias(apt_get='apt-get')
>>> from mysh import apt_get
>>> apt_get
apt-get (raise_on_error=True)

A builtin ``Shell`` instance with common options and aliases is already
available as the ``ush.sh`` module:

>>> import ush.sh as s
>>> s #doctest: +ELLIPSIS
<ush.Shell object at 0x...>

This feature is inspired by `sh.py http://amoffat.github.io/sh/`.
