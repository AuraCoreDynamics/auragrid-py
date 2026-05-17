import pytest
from unittest.mock import MagicMock
from auragrid.storage_client import StorageClient

@pytest.fixture
def mock_ipc():
    return MagicMock()

def test_write(mock_ipc):
    mock_ipc.post.return_value.status_code = 204
    
    client = StorageClient(mock_ipc)
    client.write("test.bin", b"hello")
    
    mock_ipc.post.assert_called_once_with(
        "/cell/storage/write",
        params={"path": "test.bin"},
        content=b"hello"
    )

def test_append(mock_ipc):
    mock_ipc.post.return_value.status_code = 200
    mock_ipc.post.return_value.json.return_value = {"length": 10}
    
    client = StorageClient(mock_ipc)
    length = client.append("test.bin", b"append")
    
    assert length == 10
    mock_ipc.post.assert_called_once_with(
        "/cell/storage/append",
        params={"path": "test.bin"},
        content=b"append"
    )

def test_write_with_fencing(mock_ipc):
    mock_ipc.post.return_value.status_code = 204
    
    client = StorageClient(mock_ipc)
    client.write("fenced.bin", b"data", fencing_token=123)
    
    mock_ipc.post.assert_called_once_with(
        "/cell/storage/write",
        params={"path": "fenced.bin", "fencingToken": "123"},
        content=b"data"
    )

def test_append_with_fencing(mock_ipc):
    mock_ipc.post.return_value.status_code = 200
    mock_ipc.post.return_value.json.return_value = {"length": 100}
    
    client = StorageClient(mock_ipc)
    client.append("fenced.bin", b"more", fencing_token=123)
    
    mock_ipc.post.assert_called_once_with(
        "/cell/storage/append",
        params={"path": "fenced.bin", "fencingToken": "123"},
        content=b"more"
    )

def test_delete(mock_ipc):
    mock_ipc.delete.return_value.status_code = 200
    mock_ipc.delete.return_value.json.return_value = {"deleted": True}
    
    client = StorageClient(mock_ipc)
    deleted = client.delete("test.bin", recursive=True)
    
    assert deleted is True
    mock_ipc.delete.assert_called_once_with(
        "/cell/storage/delete",
        params={"path": "test.bin", "recursive": "true"}
    )
