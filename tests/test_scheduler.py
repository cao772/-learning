import datetime as dt
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from hub.sync_loop import tick
from hub.manage import require_collection_success


class SchedulerTests(unittest.TestCase):
    def test_scheduled_at_two_beijing_time(self):
        with tempfile.TemporaryDirectory() as root:
            marker = Path(root) / 'last.json'
            with patch('hub.sync_loop.subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run:
                tick(marker, dt.datetime(2026, 10, 29, 1, 59))
                self.assertNotIn('--collect', run.call_args.args[0])
                tick(marker, dt.datetime(2026, 10, 29, 2, 0))
                self.assertIn('--collect', run.call_args.args[0])

    def test_all_source_errors_are_failure_and_partial_success_is_usable(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root)
            (source / '收件箱').mkdir()
            status = source / '收件箱/status.json'
            status.write_text(json.dumps({'sources': [{'status': 'error'}, {'status': 'http_error'}]}))
            with self.assertRaises(RuntimeError):
                require_collection_success(source)
            status.write_text(json.dumps({'sources': [{'status': 'error'}, {'status': 'ok'}]}))
            require_collection_success(source)

    def test_corrupt_marker_recovers_and_collects_only_once(self):
        with tempfile.TemporaryDirectory() as root:
            marker = Path(root) / 'last.json'
            marker.write_text('{broken')
            now = dt.datetime(2026, 10, 15, 10)
            with patch('hub.sync_loop.subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run:
                self.assertTrue(tick(marker, now))
                self.assertIn('--collect', run.call_args.args[0])
                self.assertEqual(json.loads(marker.read_text())['day'], '2026-10-15')
                self.assertTrue(tick(marker, now))
                self.assertNotIn('--collect', run.call_args.args[0])

    def test_timeout_does_not_mark_collection_complete(self):
        with tempfile.TemporaryDirectory() as root:
            marker = Path(root) / 'last.json'
            with patch('hub.sync_loop.subprocess.run', side_effect=subprocess.TimeoutExpired('sync', 240)):
                self.assertFalse(tick(marker, dt.datetime(2026, 10, 15, 10)))
            self.assertFalse(marker.exists())
