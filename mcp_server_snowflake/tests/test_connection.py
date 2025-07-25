# Copyright 2025 Snowflake Inc.
# SPDX-License-Identifier: Apache-2.0
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import json
from unittest.mock import Mock, patch

import pytest
from snowflake.connector import DictCursor
from snowflake.connector.errors import Error as SnowflakeError

from mcp_server_snowflake.connection import SnowflakeConnectionManager


@pytest.fixture
def connection_params():
    return {
        "account_identifier": "test_account",
        "username": "test_user",
        "pat": "test_pat",
        "default_session_parameters": {"TIMEZONE": "UTC"},
    }


@pytest.fixture
def connection_manager(connection_params):
    return SnowflakeConnectionManager(**connection_params)


def test_init(connection_params):
    manager = SnowflakeConnectionManager(**connection_params)

    assert manager.account_identifier == connection_params["account_identifier"]
    assert manager.username == connection_params["username"]
    assert manager.pat == connection_params["pat"]
    assert (
        manager.default_session_parameters
        == connection_params["default_session_parameters"]
    )


def test_init_without_session_params():
    manager = SnowflakeConnectionManager(
        account_identifier="test_account", username="test_user", pat="test_pat"
    )
    assert manager.default_session_parameters == {}


def test_set_query_tag(connection_manager):
    query_tag = {"app": "test_app", "user": "test_user"}
    connection_manager.set_query_tag(query_tag)

    assert connection_manager.default_session_parameters["QUERY_TAG"] == json.dumps(
        query_tag
    )


@patch("mcp_server_snowflake.connection.connect")
def test_get_connection(mock_connect, connection_manager):
    mock_cursor = Mock()
    mock_connection = Mock()
    mock_connection.cursor.return_value = mock_cursor
    mock_connect.return_value = mock_connection

    with connection_manager.get_connection() as (conn, cur):
        assert conn == mock_connection
        assert cur == mock_cursor

    mock_connect.assert_called_with(
        account=connection_manager.account_identifier,
        user=connection_manager.username,
        password=connection_manager.pat,
        session_parameters=connection_manager.default_session_parameters,
    )

    with connection_manager.get_connection(use_dict_cursor=True) as (conn, cur):
        mock_connection.cursor.assert_called_with(DictCursor)

    additional_params = {
        "role": "TEST_ROLE",
        "warehouse": "TEST_WH",
        "session_parameters": {"QUERY_TAG": "test_tag"},
    }

    with connection_manager.get_connection(**additional_params) as (conn, cur):
        expected_session_params = connection_manager.default_session_parameters.copy()
        expected_session_params.update(additional_params.pop("session_parameters"))
        mock_connect.assert_called_with(
            account=connection_manager.account_identifier,
            user=connection_manager.username,
            password=connection_manager.pat,
            session_parameters=expected_session_params,
            **additional_params,
        )


@patch("mcp_server_snowflake.connection.connect")
def test_error_handling(mock_connect, connection_manager):
    mock_connect.side_effect = SnowflakeError("Connection failed")
    with pytest.raises(SnowflakeError, match="Connection failed"):
        with connection_manager.get_connection():
            pass

    mock_cursor = Mock()
    mock_connection = Mock()
    mock_connection.cursor.return_value = mock_cursor
    mock_connect.side_effect = None
    mock_connect.return_value = mock_connection

    with pytest.raises(Exception, match="Operation failed"):
        with connection_manager.get_connection() as (conn, cur):
            raise Exception("Operation failed")

    mock_cursor.close.assert_called_once()
    mock_connection.close.assert_called_once()
