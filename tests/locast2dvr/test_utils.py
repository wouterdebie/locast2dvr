import logging
import unittest

from mock import MagicMock, patch

from locast2dvr.utils import Configuration, LoggingHandler


class TestConfiguration(unittest.TestCase):
    def test_get_configuration(self):
        args = {"key": "value",
                "another_key": "another_value"}

        config = Configuration(args)
        self.assertEqual(config.key, args["key"])
        self.assertEqual(config.another_key, args["another_key"])

    def test_del_configuration(self):
        config = Configuration({"foo": "bar"})
        del config.foo
        with self.assertRaises(AttributeError):
            config.foo

        with self.assertRaises(AttributeError):
            del config.foo

    def test_set_configuration(self):
        config = Configuration({})
        config.foo = "bar"
        self.assertEqual(config.foo, "bar")


@patch('locast2dvr.utils.isatty')
class TestLogging(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({})

    def test_logging_tty(self, isatty: MagicMock):
        self.config.verbose = 0
        self.config.logfile = None
        isatty.return_value = True
        with patch('logging.basicConfig') as logging_mock:
            LoggingHandler.init_logging(self.config)
            logging_mock.assert_called_once_with(format='%(asctime)s - %(levelname)s - %(name)s: %(message)s',
                                                 datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO)

    def test_logging_no_tty(self, isatty: MagicMock):
        self.config.verbose = 0
        self.config.logfile = None
        isatty.return_value = False
        with patch('logging.basicConfig') as logging_mock:
            LoggingHandler.init_logging(self.config)
            logging_mock.assert_called_once_with(format='%(levelname)s - %(name)s: %(message)s',
                                                 datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO)

    def test_logging_verbose(self, isatty: MagicMock):
        self.config.verbose = 1
        self.config.logfile = None
        isatty.return_value = False
        with patch('logging.basicConfig') as logging_mock:
            LoggingHandler.init_logging(self.config)
            logging_mock.assert_called_once_with(format='%(levelname)s - %(name)s: %(message)s',
                                                 datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO)

    def test_logging_debug(self, isatty: MagicMock):
        self.config.verbose = 2
        self.config.logfile = None
        isatty.return_value = False
        with patch('logging.basicConfig') as logging_mock:
            LoggingHandler.init_logging(self.config)
            logging_mock.assert_called_once_with(format='%(levelname)s - %(name)s: %(message)s',
                                                 datefmt='%Y-%m-%d %H:%M:%S', level=logging.DEBUG)

    @patch('logging.getLogger')
    @patch('logging.Formatter')
    @patch('logging.basicConfig')
    def test_logging_logfile(self, logging_mock, logging_formatter, get_logger, isatty: MagicMock):
        self.config.verbose = 0
        self.config.logfile = "foo"
        isatty.return_value = False
        with patch('logging.FileHandler') as FileHandler:
            FileHandler.return_value = fh = MagicMock()
            logging_formatter.return_value = lf = MagicMock()

            LoggingHandler.init_logging(self.config)
            fh.setFormatter.assert_called_once_with(lf)
            fh.setLevel.assert_called_once_with(logging.INFO)
            logging_formatter.assert_called()  # _once_with(
            # '%(asctime)s - %(levelname)s - %(name)s: %(message)s')
            FileHandler.assert_called_once_with("foo")
