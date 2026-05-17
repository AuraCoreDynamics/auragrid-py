import pytest
from unittest.mock import MagicMock
from auragrid.lease_client import LeaseClient, WalMarker

@pytest.fixture
def mock_ipc():
    return MagicMock()

def test_try_acquire_lease(mock_ipc):
    mock_ipc.post.return_value.status_code = 200
    mock_ipc.post.return_value.json.return_value = {
        "acquired": True,
        "lease": {
            "masId": "test-mas",
            "holderNodeId": "node-1",
            "fencingToken": 123,
            "acquiredAt": "2026-05-14T12:00:00Z",
            "expiresAt": "2026-05-14T12:00:30Z",
            "lastKnownMarker": None
        }
    }
    
    client = LeaseClient(mock_ipc)
    result = client.try_acquire_lease("test-mas", {"cpu": 100})
    
    assert result.acquired is True
    assert result.lease.fencing_token == 123
    mock_ipc.post.assert_called_once_with(
        "/cell/lease/acquire",
        json={"masId": "test-mas", "bid": {"cpu": 100}}
    )

def test_renew_lease(mock_ipc):
    mock_ipc.post.return_value.status_code = 200
    mock_ipc.post.return_value.json.return_value = {"extended": True}
    
    client = LeaseClient(mock_ipc)
    marker = WalMarker("topic-1", 42)
    extended = client.renew_lease("test-mas", 123, marker)
    
    assert extended is True
    mock_ipc.post.assert_called_once_with(
        "/cell/lease/renew",
        json={
            "masId": "test-mas",
            "fencingToken": 123,
            "marker": {"topicId": "topic-1", "sequenceNumber": 42}
        }
    )
