from . import constants
from .version import VERSION
import cache

__all__ = ['constants', 'set_constants', 'VERSION', 'cache']


def set_constants(key, value=None):
    if value is None:
        return constants.get(key)
    else:
        constants.set_value(key, value)
