import os
import logging

__author__ = 'kliner'
__version__ = '0.3.3.a0'

# init config & temp dir
home = os.path.expanduser("~")
__workdir__ = os.path.join(home, '.pybili')
if not os.path.exists(__workdir__):
    os.makedirs(__workdir__)
__loglevel__ = logging.DEBUG
