"""SondeHub telemetry objects (no network)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sondehub  # noqa: E402

FRAME = {"type": "RS41", "serial": "X1453430", "frame": 5128, "lat": 49.659469, "lon": 17.632947, "alt": 17275.8,
         "vh": 19.38, "dir": 70.4, "vv": 5.38, "sats": 11, "batt": 2.7, "freq_hz": 402100170.0, "temp": -60.1,
         "rh": 3.0, "subtype": "RS41-SG", "gps_time": 1794744283.992, "time": 1794744285.72}


class Telemetry(unittest.TestCase):
    def test_rs41(self):
        t = sondehub.telemetry(FRAME, "N0CALL", [48.1, 17.1, 150.0], "1.0beta1")
        self.assertEqual((t["manufacturer"], t["type"], t["serial"], t["frame"]), ("Vaisala", "RS41", "X1453430", 5128))
        self.assertEqual(t["datetime"], "2026-11-15T12:04:43.992Z")
        self.assertEqual(t["time_received"], "2026-11-15T12:04:45.720Z")
        self.assertEqual((t["vel_v"], t["vel_h"], t["heading"], t["humidity"], t["frequency"]), (5.38, 19.38, 70.4, 3.0, 402.1002))
        self.assertEqual((t["uploader_callsign"], t["uploader_position"], t["subtype"]), ("N0CALL", [48.1, 17.1, 150.0], "RS41-SG"))

    def test_not_sent(self):
        for change in ({"lat": None}, {"gps_time": None}, {"encrypted": True}, {"type": "M20", "serial_raw": True},
                       {"type": "DFM", "serial": "DFM-402.500"}, {"serial": None}, {"type": "RS92"}):
            self.assertIsNone(sondehub.telemetry(dict(FRAME, **change), "N0CALL"), change)

    def test_dfm_m20(self):
        t = sondehub.telemetry(dict(FRAME, type="DFM", serial="DFM-23038743", subtype="DFM17", frame=12), "N0CALL")
        self.assertEqual((t["manufacturer"], t["type"], t["subtype"], t["serial"], t["frame"]),
                         ("Graw", "DFM", "DFM17", "23038743", 1794744283))
        t = sondehub.telemetry(dict(FRAME, type="DFM", serial="DFM-23038743", subtype="DFM17P"), "N0CALL")
        self.assertNotIn("subtype", t)
        t = sondehub.telemetry(dict(FRAME, type="M20", serial="M20-507-2-02967", subtype=None), "N0CALL")
        self.assertEqual((t["manufacturer"], t["type"], t["subtype"], t["serial"]),
                         ("Meteomodem", "M20", "M20", "507-2-02967"))

    def test_queue(self):
        h = sondehub.SondeHub(callsign=lambda: "N0CALL", position=lambda: None)
        h.enabled = True                    # without the upload thread
        h.add(FRAME)
        h.add(dict(FRAME, type="DFM", serial="DFM-403.300"))
        self.assertEqual(h.info()["queued"], 1)
        h2 = sondehub.SondeHub(callsign=lambda: "", position=lambda: None)
        h2.enabled = True
        h2.add(FRAME)
        self.assertEqual(h2.info()["queued"], 0)


class Answers(unittest.TestCase):
    """SondeHub's answers: 202 with errors for all frames = refused; "unknown to us" = not validated (blocked)."""

    def put(self, status, text, n=2):
        import io
        import urllib.request
        h = sondehub.SondeHub(callsign=lambda: "N0CALL", position=lambda: None)

        class R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        r = R(text.encode())
        r.status = status
        old = urllib.request.urlopen
        urllib.request.urlopen = lambda req, timeout=None: r
        try:
            return h, h._put(sondehub.TELEMETRY_URL, [{}] * n)
        finally:
            urllib.request.urlopen = old

    def test_unknown_software(self):
        h, (status, err, bad) = self.put(202, '{"message": "x", "errors": [{"error_message": "This software is unknown to us!"},'
                                              ' {"error_message": "This software is unknown to us!"}], "warnings": []}')
        self.assertTrue(h.blocked)
        self.assertIn("validated", err)
        self.assertEqual(bad, 2)

    def test_ok_and_partial(self):
        h, (status, err, bad) = self.put(200, "")
        self.assertEqual((status, err, bad, h.blocked), (200, None, 0, False))
        h, (status, err, bad) = self.put(202, '{"errors": [{"error_message": "bad altitude"}]}', n=3)
        self.assertEqual((err, bad, h.warn), (None, 1, "bad altitude"))


if __name__ == "__main__":
    unittest.main()
