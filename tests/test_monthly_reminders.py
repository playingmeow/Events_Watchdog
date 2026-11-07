import unittest
from datetime import date
from maintenance import due_tasks, monthly_cycle_start

TASK = {"id":"cc-5","name":"Credit card check","kind":"monthly_day","day_of_month":5,"initial_due":"2026-12-05","enabled":True,"nag_daily":True,"completed_cycles":[]}

class MonthlyReminderTests(unittest.TestCase):
    def test_before_first_cycle(self):
        self.assertEqual(due_tasks({"tasks":[TASK]}, {}, date(2026,11,20)), [])
    def test_due_on_fifth(self):
        self.assertEqual(due_tasks({"tasks":[TASK]}, {}, date(2026,12,5)), [TASK])
    def test_nags_until_done(self):
        self.assertEqual(due_tasks({"tasks":[TASK]}, {}, date(2026,12,18)), [TASK])
    def test_done_stops_current_cycle(self):
        t={**TASK,"completed_cycles":["2026-12-05"]}
        self.assertEqual(due_tasks({"tasks":[t]}, {}, date(2026,12,20)), [])
    def test_next_month_restarts(self):
        t={**TASK,"completed_cycles":["2026-12-05"]}
        self.assertEqual(due_tasks({"tasks":[t]}, {}, date(2027,1,5)), [t])
    def test_cycle_does_not_shift_after_late_done(self):
        self.assertEqual(monthly_cycle_start(TASK,date(2027,1,4)),date(2026,12,5))
    def test_new_cycle_supersedes_unfinished_old(self):
        self.assertEqual(monthly_cycle_start(TASK,date(2027,1,5)),date(2027,1,5))
