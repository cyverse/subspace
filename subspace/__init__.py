from . import constants
from .playbook import PlayBook, get_playbooks
from .version import VERSION
import cache
#TODO: Remove unused imports

def set_constants(key, value=None):
    if value is None:
        return constants.get(key)
    else:
        constants.set_value(key, value)
