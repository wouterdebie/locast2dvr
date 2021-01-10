import logging
import sys


class Configuration(dict):
    def __getattr__(self, name):
        if name in self:
            return self[name]
        else:
            raise AttributeError("No such config attribute get: " + name)

    def __setattr__(self, name, value):
        self[name] = value

    def __delattr__(self, name):
        if name in self:
            del self[name]
        else:
            raise AttributeError("No such config attribute del: " + name)


class LoggingHandler:
    def __init__(self):
        self.log = logging.getLogger(self.__class__.__name__)

    @classmethod
    def init_logging(cls, config):
        log_level = logging.DEBUG if config.verbose >= 2 else logging.INFO
        if isatty():
            logging.basicConfig(format='%(asctime)s - %(levelname)s - %(name)s: %(message)s',
                                datefmt='%Y-%m-%d %H:%M:%S', level=log_level)
        else:
            logging.basicConfig(format='%(levelname)s - %(name)s: %(message)s',
                                datefmt='%Y-%m-%d %H:%M:%S', level=log_level)


def isatty():
    return sys.stdout.isatty()
