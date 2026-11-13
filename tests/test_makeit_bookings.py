import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from makeit_bookings import upcoming_bookings, format_bookings

class MakeITBookingsTests(unittest.TestCase):
    def test_seven_calendar_days(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bookings.json"
            path.write_text(json.dumps({"bookings": [
                {"source":"SimplyBook","service":"Laser","date":"2026-11-19","time":"17:30","location":"TRL"},
                {"source":"SimplyBook","service":"Old","date":"2026-11-12","time":"10:00","location":"TRL"},
                {"source":"MakeIT Yourself","service":"3D","date":"2026-11-20","time":"10:00","location":"Tampines"}
            ]}))
            rows = upcoming_bookings(date(2026,11,13),path=path)
            self.assertEqual(len(rows),1)
            self.assertIn("TRL",format_bookings(rows))
    def test_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bookings.json"
            path.write_text('{"bookings":[]}')
            self.assertEqual(upcoming_bookings(date(2026,11,13),path=path),[])

if __name__ == "__main__":
    unittest.main()
