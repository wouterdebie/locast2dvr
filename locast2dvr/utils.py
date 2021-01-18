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


TTY_LOG_FMT = '%(asctime)s - %(levelname)s - %(name)s: %(message)s'
NO_TTY_LOG_FMT = '%(levelname)s - %(name)s: %(message)s'


class LoggingHandler:
    def __init__(self):
        self.log = logging.getLogger(self.__class__.__name__)

    @classmethod
    def init_logging(cls, config):
        log_level = logging.DEBUG if config.verbose >= 2 else logging.INFO
        tty_log_fmt = '%(asctime)s - %(levelname)s - %(name)s: %(message)s'
        if isatty():
            format = TTY_LOG_FMT
        else:
            format = NO_TTY_LOG_FMT

        logging.basicConfig(
            format=format, datefmt='%Y-%m-%d %H:%M:%S', level=log_level)

        if config.logfile:
            fh = logging.FileHandler(config.logfile)
            fh.setFormatter(logging.Formatter(TTY_LOG_FMT))
            fh.setLevel(log_level)
            logging.getLogger().addHandler(fh)


def isatty():
    return sys.stdout.isatty()
