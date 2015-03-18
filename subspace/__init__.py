from . import constants as _constants
from .playbook import PlayBook
from .logging import use_logger
from .version import VERSION

def constants(key, value=None):
    if value is None:
        return _constants.get(key)
    else:
        _constants.set(key, value)
