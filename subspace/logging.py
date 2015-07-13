import ansible.callbacks

from . import constants


__all__ = ["use_logger"]


def use_logger(logger):
    """
    :logger: Use this python logger instead of logging to a file using the
    DEFAULT_LOG_PATH.
    """
    constants.set("DEFAULT_LOG_PATH", "subspace")
    ansible.callbacks.logger = logger
