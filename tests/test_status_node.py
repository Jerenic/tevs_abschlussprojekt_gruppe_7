import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1] / "PoC" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import node  # noqa: E402


def reset_node(db_path: str = ":memory:") -> None:
    """Bring the module into a clean, ready state for a single test."""
    node.init_db(db_path)
    node.PEER_URLS = []
    node.NODE_NAME = "Test-Node"
    node.READY = True
    node.NODE_STATE = "ready"
    node.pending_replications.clear()


class CrudAndValidationTest(unittest.TestCase):
    def setUp(self):
        reset_node()
        self.client = node.app.test_client()

    def test_post_status_stores_status(self):
        response = self.client.post("/status", json={
            "username": "RECON-01",
            "statustext": "Am Weg zum Einsatz",
            "latitude": 48.215,
            "longitude": 16.385,
            "uhrzeit": "2026-06-02T12:00:00+00:00",
        })

        self.assertEqual(response.status_code, 201)
        self.assertIn("RECON-01", node.statuses)
        self.assertEqual(node.statuses["RECON-01"]["statustext"], "Am Weg zum Einsatz")

    def test_get_one_returns_stored_status(self):
        self.client.post("/status", json={
            "username": "RECON-09",
            "statustext": "Position gehalten",
            "latitude": 48.2,
            "longitude": 16.3,
        })

        response = self.client.get("/status/RECON-09")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["username"], "RECON-09")

    def test_get_unknown_user_returns_404(self):
        self.assertEqual(self.client.get("/status/UNKNOWN").status_code, 404)

    def test_post_without_username_is_rejected(self):
        response = self.client.post("/status", json={"statustext": "x", "latitude": 1.0, "longitude": 2.0})
        self.assertEqual(response.status_code, 400)

    def test_post_without_statustext_is_rejected(self):
        response = self.client.post("/status", json={"username": "A", "latitude": 1.0, "longitude": 2.0})
        self.assertEqual(response.status_code, 400)

    def test_post_with_non_numeric_coordinates_is_rejected(self):
        response = self.client.post("/status", json={
            "username": "A", "statustext": "x", "latitude": "nope", "longitude": 2.0,
        })
        self.assertEqual(response.status_code, 400)

    def test_post_with_invalid_timestamp_is_rejected(self):
        response = self.client.post("/status", json={
            "username": "A", "statustext": "x", "latitude": 1.0, "longitude": 2.0, "uhrzeit": "gestern",
        })
        self.assertEqual(response.status_code, 400)

    def test_post_with_deleted_flag_is_rejected(self):
        response = self.client.post("/status", json={
            "username": "A", "statustext": "x", "latitude": 1.0, "longitude": 2.0, "deleted": True,
        })
        self.assertEqual(response.status_code, 400)

    def test_non_dict_payload_is_rejected(self):
        response = self.client.post("/status", data="[]", content_type="application/json")
        self.assertEqual(response.status_code, 400)


class ReplicationAndConflictTest(unittest.TestCase):
    def setUp(self):
        reset_node()
        self.client = node.app.test_client()

    def test_post_status_replicates_to_configured_peers(self):
        node.PEER_URLS = ["http://peer-a:5000"]
        mocked_response = Mock(ok=True, status_code=200)

        with patch("node.requests.post", return_value=mocked_response) as mocked_post:
            response = self.client.post("/status", json={
                "username": "RECON-02", "statustext": "Bereit",
                "latitude": 48.2, "longitude": 16.3, "uhrzeit": "2026-06-02T12:00:00+00:00",
            })

        self.assertEqual(response.status_code, 201)
        mocked_post.assert_called_once()
        self.assertEqual(mocked_post.call_args.args[0], "http://peer-a:5000/replicate")

    def test_replicate_ignores_older_update(self):
        self.client.post("/status", json={
            "username": "RECON-03", "statustext": "Neuer Stand",
            "latitude": 48.2, "longitude": 16.3, "uhrzeit": "2026-06-02T12:00:00+00:00",
        })

        response = self.client.post("/replicate", json={
            "username": "RECON-03", "statustext": "Alter Stand",
            "latitude": 48.0, "longitude": 16.0, "uhrzeit": "2026-06-01T12:00:00+00:00",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(node.statuses["RECON-03"]["statustext"], "Neuer Stand")

    def test_replicate_applies_newer_update(self):
        self.client.post("/status", json={
            "username": "RECON-05", "statustext": "Alt",
            "latitude": 48.2, "longitude": 16.3, "uhrzeit": "2026-06-01T12:00:00+00:00",
        })

        self.client.post("/replicate", json={
            "username": "RECON-05", "statustext": "Neu",
            "latitude": 48.2, "longitude": 16.3, "uhrzeit": "2026-06-02T12:00:00+00:00",
        })

        self.assertEqual(node.statuses["RECON-05"]["statustext"], "Neu")

    def test_equal_timestamp_tiebreak_is_deterministic(self):
        same_time = "2026-06-02T12:00:00+00:00"
        node.apply_status({
            "username": "TIE", "statustext": "from-a", "uhrzeit": same_time,
            "latitude": 1.0, "longitude": 2.0, "deleted": False, "originNode": "Node-A",
        })

        # Higher originNode wins the tie -> applied
        self.client.post("/replicate", json={
            "username": "TIE", "statustext": "from-b", "uhrzeit": same_time,
            "latitude": 1.0, "longitude": 2.0, "originNode": "Node-B",
        })
        self.assertEqual(node.statuses["TIE"]["statustext"], "from-b")

        # Lower originNode loses the tie -> ignored
        self.client.post("/replicate", json={
            "username": "TIE", "statustext": "from-a-again", "uhrzeit": same_time,
            "latitude": 1.0, "longitude": 2.0, "originNode": "Node-A",
        })
        self.assertEqual(node.statuses["TIE"]["statustext"], "from-b")


class TombstoneTest(unittest.TestCase):
    def setUp(self):
        reset_node()
        self.client = node.app.test_client()

    def test_delete_creates_tombstone_and_hides_status(self):
        self.client.post("/status", json={
            "username": "RECON-04", "statustext": "Aktiv", "latitude": 48.2, "longitude": 16.3,
        })

        delete_response = self.client.delete("/status/RECON-04")
        list_response = self.client.get("/status")

        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(node.statuses["RECON-04"]["deleted"])
        self.assertEqual(list_response.json, [])

    def test_delete_replicates_tombstone_to_peers(self):
        node.PEER_URLS = ["http://peer-a:5000"]
        self.client.post("/status", json={
            "username": "RECON-06", "statustext": "Aktiv", "latitude": 48.2, "longitude": 16.3,
        })

        with patch("node.requests.post", return_value=Mock(ok=True, status_code=200)) as mocked_post:
            self.client.delete("/status/RECON-06")

        self.assertEqual(mocked_post.call_args.args[0], "http://peer-a:5000/replicate")
        self.assertTrue(mocked_post.call_args.kwargs["json"]["deleted"])

    def test_old_update_does_not_resurrect_deleted_status(self):
        self.client.post("/replicate", json={
            "username": "GHOST", "statustext": "", "deleted": True,
            "uhrzeit": "2026-06-02T12:00:00+00:00", "originNode": "Node-A",
        })

        # An older, non-deleted replicate must not bring the status back.
        self.client.post("/replicate", json={
            "username": "GHOST", "statustext": "wieder da",
            "latitude": 48.2, "longitude": 16.3, "uhrzeit": "2026-06-01T12:00:00+00:00",
        })

        self.assertTrue(node.statuses["GHOST"]["deleted"])
        self.assertEqual(self.client.get("/status").json, [])
        self.assertEqual(self.client.get("/status/GHOST").status_code, 404)


class PersistenceTest(unittest.TestCase):
    def setUp(self):
        test_tmp_root = Path(__file__).resolve().parents[1] / ".test-tmp"
        test_tmp_root.mkdir(exist_ok=True)
        self.tmpdir = str(test_tmp_root / str(uuid.uuid4()))
        os.makedirs(self.tmpdir, exist_ok=False)
        self.db_path = os.path.join(self.tmpdir, "status.db")
        reset_node(self.db_path)
        self.client = node.app.test_client()

    def tearDown(self):
        reset_node()  # close file-backed connection, switch back to in-memory
        try:
            os.remove(self.db_path)
        except OSError:
            pass
        try:
            os.rmdir(self.tmpdir)
        except OSError:
            pass

    def test_status_survives_reopen(self):
        self.client.post("/status", json={
            "username": "PERSIST-01", "statustext": "bleibt erhalten",
            "latitude": 48.2, "longitude": 16.3, "uhrzeit": "2026-06-02T12:00:00+00:00",
        })

        # Re-open the same database file (simulates a container restart).
        node.init_db(self.db_path)

        self.assertIn("PERSIST-01", node.statuses)
        self.assertEqual(node.statuses["PERSIST-01"]["statustext"], "bleibt erhalten")

    def test_tombstone_survives_reopen(self):
        self.client.post("/status", json={
            "username": "PERSIST-02", "statustext": "aktiv", "latitude": 48.2, "longitude": 16.3,
        })
        self.client.delete("/status/PERSIST-02")

        node.init_db(self.db_path)

        self.assertTrue(node.statuses["PERSIST-02"]["deleted"])
        self.assertEqual(self.client.get("/status").json, [])


class BootstrapTest(unittest.TestCase):
    def setUp(self):
        reset_node()

    def _snapshot_response(self, statuses):
        response = Mock(ok=True)
        response.json = lambda: {"node": "Peer", "statuses": statuses}
        return response

    def test_bootstrap_merges_peer_snapshot(self):
        snapshot = self._snapshot_response([{
            "username": "B1", "statustext": "von Peer", "uhrzeit": "2026-06-02T10:00:00+00:00",
            "latitude": 1.0, "longitude": 2.0, "deleted": False, "originNode": "Peer",
        }])

        with patch("node.requests.get", return_value=snapshot):
            applied = node.bootstrap_from_peers(["http://peer:5000"], timeout=1)

        self.assertEqual(applied, 1)
        self.assertIn("B1", node.statuses)

    def test_bootstrap_does_not_override_newer_local(self):
        node.apply_status({
            "username": "B2", "statustext": "lokal neu", "uhrzeit": "2026-06-03T10:00:00+00:00",
            "latitude": 1.0, "longitude": 2.0, "deleted": False, "originNode": "Test-Node",
        })
        snapshot = self._snapshot_response([{
            "username": "B2", "statustext": "peer alt", "uhrzeit": "2026-06-01T10:00:00+00:00",
            "latitude": 1.0, "longitude": 2.0, "deleted": False, "originNode": "Peer",
        }])

        with patch("node.requests.get", return_value=snapshot):
            node.bootstrap_from_peers(["http://peer:5000"], timeout=1)

        self.assertEqual(node.statuses["B2"]["statustext"], "lokal neu")

    def test_bootstrap_without_peers_returns_zero(self):
        self.assertEqual(node.bootstrap_from_peers([], timeout=1), 0)


class GracePeriodTest(unittest.TestCase):
    def setUp(self):
        reset_node()
        self.client = node.app.test_client()
        node.READY = False
        node.NODE_STATE = "bootstrapping"

    def tearDown(self):
        node.READY = True
        node.NODE_STATE = "ready"

    def test_client_endpoints_blocked_during_bootstrap(self):
        self.assertEqual(self.client.get("/status").status_code, 503)
        self.assertEqual(self.client.post("/status", json={
            "username": "X", "statustext": "y", "latitude": 1.0, "longitude": 2.0,
        }).status_code, 503)
        self.assertEqual(self.client.delete("/status/X").status_code, 503)

    def test_health_and_replicate_work_during_bootstrap(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        replicate = self.client.post("/replicate", json={
            "username": "R", "statustext": "y", "latitude": 1.0, "longitude": 2.0,
            "uhrzeit": "2026-06-02T12:00:00+00:00",
        })
        self.assertEqual(replicate.status_code, 200)


class RetryTest(unittest.TestCase):
    def setUp(self):
        reset_node()
        node.PEER_URLS = ["http://peer:5000"]

    def _status(self, text="x", uhrzeit="2026-06-02T12:00:00+00:00"):
        return {
            "username": "RETRY-01", "statustext": text, "uhrzeit": uhrzeit,
            "latitude": 1.0, "longitude": 2.0, "deleted": False, "originNode": "Test-Node",
        }

    def test_failed_replication_is_queued(self):
        with patch("node.requests.post", side_effect=node.requests.RequestException("down")):
            node.replicate_to_peers(self._status())

        self.assertEqual(len(node.pending_replications), 1)

    def test_pending_is_flushed_on_recovery(self):
        with patch("node.requests.post", side_effect=node.requests.RequestException("down")):
            node.replicate_to_peers(self._status())

        with patch("node.requests.post", return_value=Mock(ok=True, status_code=200)):
            flushed = node.process_pending()

        self.assertEqual(flushed, 1)
        self.assertEqual(len(node.pending_replications), 0)

    def test_pending_dedup_keeps_newest_per_peer_and_user(self):
        with patch("node.requests.post", side_effect=node.requests.RequestException("down")):
            node.replicate_to_peers(self._status("alt", "2026-06-01T12:00:00+00:00"))
            node.replicate_to_peers(self._status("neu", "2026-06-02T12:00:00+00:00"))

        self.assertEqual(len(node.pending_replications), 1)
        self.assertEqual(node.pending_replications[0]["status"]["statustext"], "neu")


if __name__ == "__main__":
    unittest.main()
