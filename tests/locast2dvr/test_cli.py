import unittest

from click.testing import CliRunner
from mock import MagicMock, patch

from locast2dvr.cli import cli


class TestApp(unittest.TestCase):
    @patch('locast2dvr.cli.Configuration')
    @patch('locast2dvr.cli.Main')
    def test_cli(self, main_mock: MagicMock, config_mock: MagicMock):
        cli_instance = MagicMock()
        main_mock.return_value = cli_instance
        config_instance = MagicMock()
        config_mock.return_value = config_instance

        runner = CliRunner()
        runner.invoke(cli, ['-U', 'foo',
                            '-P', 'bar'])

        main_mock.assert_called_once_with(config_instance)
        cli_instance.start.assert_called_once()
