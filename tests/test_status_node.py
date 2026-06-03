import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from status_node import app as app_module  # noqa: E402
from status_node import bootstrap, config, models, replication, storage  # noqa: E402


def reset_node(db_path: str = ":memory:") -> None:
    """Bring the modules into a clean, ready state for a single test."""
    storage.init_db(db_path)
    config.PEER_URLS = []
    config.NODE_NAME = "Test-Node"
    bootstrap.READY = True
    bootstrap.NODE_STATE = "ready"
    replication.pending_replications.clear()


class CrudAndValidationTest(unittest.TestCase):
    def setUp(self):
        reset_node()
        self.client = app_module.app.test_client()

    def test_post_status_stores_status(self):
        response = self.client.post("/status", json={
            "username": "RECON-01",
            "statustext": "Am Weg zum Einsatz",
            "latitude": 48.215,
            "longitude": 16.385,
            "uhrzeit": "2026-06-02T12:00:00+00:00",
        })

        self.assertEqual(response.status_code, 201)
        self.assertIn("RECON-01", storage.statuses)
        self.assertEqual(storage.statuses["RECON-01"]["statustext"], "Am Weg zum Einsatz")

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
        self.client = app_module.app.test_client()

    def test_post_status_replicates_to_configured_peers(self):
        config.PEER_URLS = ["http://peer-a:5000"]
        mocked_response = Mock(ok=True, status_code=200)

        with patch("status_node.replication.requests.post", return_value=mocked_response) as mocked_post:
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
        self.assertEqual(storage.statuses["RECON-03"]["statustext"], "Neuer Stand")

    def test_replicate_applies_newer_update(self):
        self.client.post("/status", json={
            "username": "RECON-05", "statustext": "Alt",
            "latitude": 48.2, "longitude": 16.3, "uhrzeit": "2026-06-01T12:00:00+00:00",
        })

        self.client.post("/replicate", json={
            "username": "RECON-05", "statustext": "Neu",
            "latitude": 48.2, "longitude": 16.3, "uhrzeit": "2026-06-02T12:00:00+00:00",
        })

        self.assertEqual(storage.statuses["RECON-05"]["statustext"], "Neu")

    def test_equal_timestamp_tiebreak_is_deterministic(self):
        same_time = "2026-06-02T12:00:00+00:00"
        storage.apply_status({
            "username": "TIE", "statustext": "from-a", "uhrzeit": same_time,
            "latitude": 1.0, "longitude": 2.0, "deleted": False, "originNode": "Node-A",
        })

        # Higher originNode wins the tie -> applied
        self.client.post("/replicate", json={
            "username": "TIE", "statustext": "from-b", "uhrzeit": same_time,
            "latitude": 1.0, "longitude": 2.0, "originNode": "Node-B",
        })
        self.assertEqual(storage.statuses["TIE"]["statustext"], "from-b")

        # Lower originNode loses the tie -> ignored
        self.client.post("/replicate", json={
            "username": "TIE", "statustext": "from-a-again", "uhrzeit": same_time,
            "latitude": 1.0, "longitude": 2.0, "originNode": "Node-A",
        })
        self.assertEqual(storage.statuses["TIE"]["statustext"], "from-b")


class TombstoneTest(unittest.TestCase):
    def setUp(self):
        reset_node()
        self.client = app_module.app.test_client()

    def test_delete_creates_tombstone_and_hides_status(self):
        self.client.post("/status", json={
            "username": "RECON-04", "statustext": "Aktiv", "latitude": 48.2, "longitude": 16.3,
        })

        delete_response = self.client.delete("/status/RECON-04")
        list_response = self.client.get("/status")

        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(storage.statuses["RECON-04"]["deleted"])
        self.assertEqual(list_response.json, [])

    def test_delete_replicates_tombstone_to_peers(self):
        config.PEER_URLS = ["http://peer-a:5000"]
        self.client.post("/status", json={
            "username": "RECON-06", "statustext": "Aktiv", "latitude": 48.2, "longitude": 16.3,
        })

        with patch("status_node.replication.requests.post", return_value=Mock(ok=True, status_code=200)) as mocked_post:
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

        self.assertTrue(storage.statuses["GHOST"]["deleted"])
        self.assertEqual(self.client.get("/status").json, [])
        self.assertEqual(self.client.get("/status/GHOST").status_code, 404)


class PersistenceTest(unittest.TestCase):
    def setUp(self):
        self.old_journal_mode = os.environ.get("SQLITE_JOURNAL_MODE")
        os.environ["SQLITE_JOURNAL_MODE"] = "MEMORY"
        self.tmpdir = Path(__file__).resolve().parents[1] / ".test-tmp" / uuid4().hex
        self.tmpdir.mkdir(parents=True, exist_ok=True)
        self.db_path = str(self.tmpdir / "status.db")
        reset_node(self.db_path)
        self.client = app_module.app.test_client()

    def tearDown(self):
        reset_node()  # close file-backed connection, switch back to in-memory
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        if self.old_journal_mode is None:
            os.environ.pop("SQLITE_JOURNAL_MODE", None)
        else:
            os.environ["SQLITE_JOURNAL_MODE"] = self.old_journal_mode

    def test_status_survives_reopen(self):
        self.client.post("/status", json={
            "username": "PERSIST-01", "statustext": "bleibt erhalten",
            "latitude": 48.2, "longitude": 16.3, "uhrzeit": "2026-06-02T12:00:00+00:00",
        })

        # Re-open the same database file (simulates a container restart).
        storage.init_db(self.db_path)

        self.assertIn("PERSIST-01", storage.statuses)
        self.assertEqual(storage.statuses["PERSIST-01"]["statustext"], "bleibt erhalten")

    def test_tombstone_survives_reopen(self):
        self.client.post("/status", json={
            "username": "PERSIST-02", "statustext": "aktiv", "latitude": 48.2, "longitude": 16.3,
        })
        self.client.delete("/status/PERSIST-02")

        storage.init_db(self.db_path)

        self.assertTrue(storage.statuses["PERSIST-02"]["deleted"])
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

        with patch("status_node.bootstrap.requests.get", return_value=snapshot):
            applied = bootstrap.bootstrap_from_peers(["http://peer:5000"], timeout=1)

        self.assertEqual(applied, 1)
        self.assertIn("B1", storage.statuses)

    def test_bootstrap_does_not_override_newer_local(self):
        storage.apply_status({
            "username": "B2", "statustext": "lokal neu", "uhrzeit": "2026-06-03T10:00:00+00:00",
            "latitude": 1.0, "longitude": 2.0, "deleted": False, "originNode": "Test-Node",
        })
        snapshot = self._snapshot_response([{
            "username": "B2", "statustext": "peer alt", "uhrzeit": "2026-06-01T10:00:00+00:00",
            "latitude": 1.0, "longitude": 2.0, "deleted": False, "originNode": "Peer",
        }])

        with patch("status_node.bootstrap.requests.get", return_value=snapshot):
            bootstrap.bootstrap_from_peers(["http://peer:5000"], timeout=1)

        self.assertEqual(storage.statuses["B2"]["statustext"], "lokal neu")

    def test_bootstrap_without_peers_returns_zero(self):
        self.assertEqual(bootstrap.bootstrap_from_peers([], timeout=1), 0)


class GracePeriodTest(unittest.TestCase):
    def setUp(self):
        reset_node()
        self.client = app_module.app.test_client()
        bootstrap.READY = False
        bootstrap.NODE_STATE = "bootstrapping"

    def tearDown(self):
        bootstrap.READY = True
        bootstrap.NODE_STATE = "ready"

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
        config.PEER_URLS = ["http://peer:5000"]

    def _status(self, text="x", uhrzeit="2026-06-02T12:00:00+00:00"):
        return {
            "username": "RETRY-01", "statustext": text, "uhrzeit": uhrzeit,
            "latitude": 1.0, "longitude": 2.0, "deleted": False, "originNode": "Test-Node",
        }

    def test_failed_replication_is_queued(self):
        with patch("status_node.replication.requests.post", side_effect=replication.requests.RequestException("down")):
            replication.replicate_to_peers(self._status())

        self.assertEqual(len(replication.pending_replications), 1)

    def test_pending_is_flushed_on_recovery(self):
        with patch("status_node.replication.requests.post", side_effect=replication.requests.RequestException("down")):
            replication.replicate_to_peers(self._status())

        with patch("status_node.replication.requests.post", return_value=Mock(ok=True, status_code=200)):
            flushed = replication.process_pending()

        self.assertEqual(flushed, 1)
        self.assertEqual(len(replication.pending_replications), 0)

    def test_pending_dedup_keeps_newest_per_peer_and_user(self):
        with patch("status_node.replication.requests.post", side_effect=replication.requests.RequestException("down")):
            replication.replicate_to_peers(self._status("alt", "2026-06-01T12:00:00+00:00"))
            replication.replicate_to_peers(self._status("neu", "2026-06-02T12:00:00+00:00"))

        self.assertEqual(len(replication.pending_replications), 1)
        self.assertEqual(replication.pending_replications[0]["status"]["statustext"], "neu")


class ConfigTest(unittest.TestCase):
    def tearDown(self):
        # Restore defaults so other tests are unaffected.
        config.NODE_NAME = "Test-Node"
        config.PEER_URLS = []

    def test_load_prefers_cli_args_when_env_absent(self):
        with patch.dict(os.environ, {}, clear=True):
            config.load(["prog", "5005", "http://p1:5000,http://p2:5000/", "Node-X", "node-x.db"])

        self.assertEqual(config.PORT, 5005)
        self.assertEqual(config.PEER_URLS, ["http://p1:5000", "http://p2:5000"])
        self.assertEqual(config.NODE_NAME, "Node-X")
        self.assertEqual(config.DB_PATH, "node-x.db")

    def test_load_prefers_env_over_cli(self):
        with patch.dict(os.environ, {"NODE_NAME": "Env-Node", "PORT": "6001"}, clear=True):
            config.load(["prog", "5000", "", "Cli-Node"])

        self.assertEqual(config.NODE_NAME, "Env-Node")
        self.assertEqual(config.PORT, 6001)


class StorageIsolationTest(unittest.TestCase):
    def test_reinit_resets_cache_for_isolation(self):
        storage.init_db(":memory:")
        storage.apply_status({
            "username": "ISO-1", "statustext": "x", "uhrzeit": "2026-06-02T12:00:00+00:00",
            "latitude": 1.0, "longitude": 2.0, "deleted": False, "originNode": "Test-Node",
        })
        self.assertIn("ISO-1", storage.statuses)

        # A fresh in-memory DB must start empty (independent store).
        storage.init_db(":memory:")
        self.assertEqual(storage.statuses, {})


if __name__ == "__main__":
    unittest.main()
