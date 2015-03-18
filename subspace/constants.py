import sys

from ansible import constants as ansible_constants


def set(key, value):
    setattr(ansible_constants, key, value)


def get(key):
    return getattr(ansible_constants, key)
