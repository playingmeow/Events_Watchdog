"""Date-exact one-off reminders: no early send, no repeated or late send."""
import unittest
from datetime import date
from maintenance import due_tasks, due_date

TASK = {"id":"hirosaki-sakura-final-2027","name":"Hirosaki Sakura Festival — Final 2027 Check","kind":"one_off","initial_due":"2027-04-23","nag_daily":False,"enabled":True}

class OneOffReminderTests(unittest.TestCase):
    def test_before_date(self):
        self.assertEqual(due_tasks({"tasks":[TASK]}, {}, date(2027,4,22)), [])
    def test_on_date(self):
        self.assertEqual(due_tasks({"tasks":[TASK]}, {}, date(2027,4,23)), [TASK])
    def test_sent_same_day(self):
        self.assertEqual(due_tasks({"tasks":[TASK]}, {TASK["id"]:"sent"}, date(2027,4,23)), [])
    def test_expired(self):
        self.assertEqual(due_tasks({"tasks":[TASK]}, {}, date(2027,4,24)), [])
    def test_disabled(self):
        self.assertEqual(due_tasks({"tasks":[{**TASK,"enabled":False}]}, {}, date(2027,4,23)), [])
    def test_exact_due_date(self):
        self.assertEqual(due_date(TASK),date(2027,4,23))
