import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from lumalock import protocol as b


class QueryRecoveryTests(unittest.TestCase):
    def test_stale_restricted_response_retried_without_lut_writes(self):
        expected=bytes(range(16))
        t=SimpleNamespace(panel_edid=expected,table=Mock(side_effect=[bytes(256)]+[expected+bytes(240)]*6))
        with patch.object(b,'stable'):
            self.assertTrue(b.restricted(t))
        self.assertEqual(t.table.call_count,7)

    def test_open_window_never_accepted(self):
        t=SimpleNamespace(panel_edid=bytes(range(16)),table=Mock(return_value=bytes(256)))
        with patch.object(b,'stable'):self.assertFalse(b.restricted(t))

    def test_transient_cleanup_failure_retries_without_touching_curve(self):
        t=Mock();t.native.return_value=0
        with patch.object(b,'restricted',side_effect=[False,True]),patch.object(b,'stable',return_value=b.profile.BASELINE):
            r=b.restore_window(t)
        self.assertTrue(b.window_ok(r));self.assertEqual(r['attempts'],2)
        t.lut_packet.assert_not_called()

    def test_permanent_cleanup_failure_is_still_failure(self):
        t=Mock();t.native.return_value=0
        with patch.object(b,'restricted',return_value=False),patch.object(b,'stable',return_value=b.profile.BASELINE):
            r=b.restore_window(t)
        self.assertFalse(b.window_ok(r));self.assertEqual(r['attempts'],3)

    def test_expected_register_ignores_stable_stale_values(self):
        t=Mock();t.read_at.side_effect=[b'xx']*3+[b'ok']*6
        with patch.object(b.time,'sleep'):
            self.assertEqual(b.stable(t,0x500,2,b'ok'),b'ok')

    def test_persistent_register_corruption_rejected(self):
        t=Mock();t.read_at.return_value=b'xx'
        with patch.object(b.time,'sleep'),self.assertRaises(RuntimeError):b.stable(t,0x500,2,b'ok')
