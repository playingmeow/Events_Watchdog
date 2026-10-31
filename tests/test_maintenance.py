import unittest
from datetime import date
from maintenance import due_date, due_tasks

class MaintenanceTests(unittest.TestCase):
    def test_due_dates(self):
        self.assertEqual(due_date({"last_done":"2026-10-24","interval_days":60}), date(2026,12,23))
        self.assertEqual(due_date({"last_done":None,"initial_due":"2026-10-31","interval_days":30}), date(2026,10,31))

    def test_done_resets_countdown(self):
        task = {"id":"sensors","name":"Sensors","last_done":"2026-10-31","interval_days":30}
        self.assertEqual(due_tasks({"tasks":[task]}, {}, date(2026,11,1)), [])
        self.assertEqual(len(due_tasks({"tasks":[task]}, {}, date(2026,11,30))), 1)

    def test_only_one_alert_per_cycle(self):
        task = {"id":"dust-bag","last_done":"2026-10-01","interval_days":30}
        data = {"tasks":[task]}
        self.assertEqual(len(due_tasks(data, {}, date(2026,11,1))), 1)
        self.assertEqual(due_tasks(data, {"dust-bag":"2026-10-01"}, date(2026,11,1)), [])
        task["last_done"] = "2026-11-01"
        self.assertEqual(due_tasks(data, {"dust-bag":"2026-10-01"}, date(2026,11,2)), [])

if __name__ == "__main__":
    unittest.main()
