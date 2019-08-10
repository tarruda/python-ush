from setuptools import setup


VERSION = '4.0.0'
REPO    = 'https://github.com/tarruda/python-ush'

setup(
  name='ush',
  py_modules=['ush'],
  version=VERSION,
  description='Powerful API for invoking with external commands',
  author='Thiago de Arruda',
  author_email='tpadilha84@gmail.com',
  license='MIT',
  url=REPO,
  download_url='{0}/archive/{1}.tar.gz'.format(REPO, VERSION),
  keywords=['sh', 'unix', 'bash', 'shell', 'glob']
)
