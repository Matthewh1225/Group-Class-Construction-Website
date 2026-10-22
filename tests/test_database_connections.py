import unittest
from unittest.mock import MagicMock, patch

from flask import Flask

from utils.database import close_database, database_cursor


class RequestConnectionTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.testing = True
        self.app.teardown_request(close_database)
        self.connection = MagicMock()
        patcher = patch("utils.database.mysql.connector.connect", return_value=self.connection)
        self.connect = patcher.start()
        self.addCleanup(patcher.stop)

    def test_helpers_share_connection_and_commit_separately(self):
        with self.app.test_request_context():
            for _ in range(2):
                with database_cursor():
                    pass
            self.connect.assert_called_once()
            self.assertEqual(self.connection.commit.call_count, 2)
            self.connection.close.assert_not_called()
        self.connection.close.assert_called_once()

    def test_failed_helper_rolls_back_and_request_can_continue(self):
        with self.app.test_request_context():
            with self.assertRaises(ValueError), database_cursor():
                raise ValueError("Failed operation")
            self.connection.rollback.assert_called_once()
            self.connection.commit.assert_not_called()
            with database_cursor():
                pass
            self.connect.assert_called_once()
        self.connection.close.assert_called_once()

    def test_unhandled_request_error_still_closes_connection(self):
        @self.app.get("/failure")
        def failure():
            with database_cursor():
                raise ValueError("Failed request")

        with self.assertRaises(ValueError):
            self.app.test_client().get("/failure")
        self.connection.rollback.assert_called_once()
        self.connection.close.assert_called_once()

    def test_requests_do_not_share_connections_even_with_outer_app_context(self):
        second = MagicMock()
        self.connect.side_effect = [self.connection, second]
        with self.app.app_context():
            for _ in range(2):
                with self.app.test_request_context(), database_cursor():
                    pass
        self.assertEqual(self.connect.call_count, 2)
        self.connection.close.assert_called_once()
        second.close.assert_called_once()

    def test_requests_without_queries_do_not_connect(self):
        with self.app.test_request_context():
            pass
        self.connect.assert_not_called()

    def test_worker_connections_close_without_request_teardown(self):
        with self.app.app_context():
            with database_cursor():
                pass
            self.connection.close.assert_called_once()
        self.connection.reset_mock()
        with self.assertRaises(ValueError), database_cursor():
            raise ValueError("Worker failed")
        self.connection.rollback.assert_called_once()
        self.connection.close.assert_called_once()
