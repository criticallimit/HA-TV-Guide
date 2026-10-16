"""Bound merge work while preserving source priority and time-window semantics."""
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch
from reference_support import app


class TimelineWorkTests(unittest.TestCase):
    def setUp(self):
        self.store = app.EPGStore('de')
        self.start = datetime(2026, 10, 25, tzinfo=timezone.utc)

    def programme(self, offset, title='Programme', rank=100):
        start = self.start + timedelta(minutes=offset)
        return {'title':title, 'start':start.isoformat(), 'end':(start+timedelta(minutes=30)).isoformat(), '_source_rank':rank}

    def test_malformed_priority_does_not_break_valid_schedule(self):
        for rank in ('bad', ['bad'], {'bad':1}, float('inf')):
            with self.subTest(rank=rank):
                first = self.programme(0, rank=rank)
                second = self.programme(10, 'Correction', rank=240)
                self.assertEqual(self.store._validate_program_timeline([first, second]), [second])

    def test_naive_candidate_cannot_replace_or_break_valid_programme(self):
        valid = self.programme(0)
        invalid = {**valid, 'start':'2026-10-25T00:01:00', 'end':'2026-10-25T00:31:00', '_source_rank':999}
        self.assertEqual(self.store._merge_program_lists([valid], [invalid]), [valid])
        self.assertEqual(self.store._merge_program_lists([invalid], [valid]), [valid])

    def test_shifted_corrections_follow_changed_start_and_utc_offsets(self):
        first = self.programme(3)
        correction = self.programme(7, rank=200)
        later = self.programme(11, rank=300)
        # The same UTC instant uses a different offset in the repeated DST hour.
        later = {**later, 'start':datetime.fromisoformat(later['start']).astimezone(timezone(timedelta(hours=2))).isoformat()}
        self.assertEqual(self.store._merge_program_lists([first], [correction, later]), [later])

    def test_large_merge_compares_nearby_slots_instead_of_entire_schedule(self):
        existing = [self.programme(i*30, str(i)) for i in range(500)]
        incoming = [self.programme(i*30+1, str(i), rank=240) for i in range(500)]
        with patch.object(self.store, '_same_programme', wraps=self.store._same_programme) as comparisons:
            result = self.store._merge_program_lists(existing, incoming)
        self.assertEqual(result, incoming)
        self.assertLess(comparisons.call_count, 500*10, 'Merge work must stay bounded per nearby time slot')
