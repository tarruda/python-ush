import os

from helper import env, s, sh


def setup_function(function):
    os.environ.clear()
    os.environ['USH_VAR1'] = 'var1'
    os.environ['USH_VAR2'] = 'var2'


def test_env_inherited_by_default():
    assert str(env) == s('USH_VAR1=var1\nUSH_VAR2=var2\n')


def test_new_env_merged_by_default():
    assert str(env(env={'USH_VAR3': 'var3', 'USH_VAR4': 'var4'})) == s(
        'USH_VAR1=var1\nUSH_VAR2=var2\nUSH_VAR3=var3\nUSH_VAR4=var4\n')


def test_env_override():
    assert str(env(merge_env=False)) == s('USH_VAR1=var1\nUSH_VAR2=var2\n')
    assert str(env(merge_env=False, env={})) == ''
    assert str(env(merge_env=False, env={
        'USH_VAR3': 'var3', 'USH_VAR4': 'var4'})) == s(
            'USH_VAR3=var3\nUSH_VAR4=var4\n')


def test_unset_env():
    assert str(env(env={'USH_VAR1': None})) == s('USH_VAR2=var2\n')
    assert str(env(env={'USH_VAR1': None, 'USH_VAR2': None})) == ''


def test_shell_setenv():
    with sh.setenv({'USH_VAR9': 'var9'}):
        assert str(env) == s('USH_VAR1=var1\nUSH_VAR2=var2\nUSH_VAR9=var9\n')
        with sh.setenv({'USH_VAR2': None}):
            assert str(env) == s('USH_VAR1=var1\nUSH_VAR9=var9\n')
            with sh.setenv({'USH_VAR9': None}):
                assert str(env) == s('USH_VAR1=var1\n')
            assert str(env) == s('USH_VAR1=var1\nUSH_VAR9=var9\n')
        assert str(env) == s('USH_VAR1=var1\nUSH_VAR2=var2\nUSH_VAR9=var9\n')
    assert str(env) == s('USH_VAR1=var1\nUSH_VAR2=var2\n')

