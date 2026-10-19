"""Review export integrity tests, all labels synthetic and never user evidence."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from hub.v6.annotation_audit import audit, validate_packet
from hub.v6.offline import packet


def read_csv(path):
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class AnnotationAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        items = [{'url': 'https://example.org/article-' + str(i),
                  'title': 'Independent article %03d' % i,
                  'summary': 'Synthetic test document (not real news)',
                  'fingerprint': str(i),
                  'published_at': '2026-10-18T04:00:00+00:00'}
                 for i in range(120)]
        scores = [{'event_id': 'event-' + str(i), 'members': [x['url']]}
                  for i, x in enumerate(items)]
        self.report = {'report_id': 'synthetic-only',
                       'items': items, 'pairs': [], 'scores': scores}
        packet(self.report, self.root)
        self.pairs = self.root / 'pair-labels.csv'
        self.relevance = self.root / 'relevance-labels.csv'

    def mark(self, pairs, rel, name):
        rows = read_csv(pairs)
        for i, row in enumerate(rows):
            row['label'] = 'same_event' if i < 5 else 'different_event'
            row['annotator'] = name
            row['provenance'] = 'human'  # synthetic fixture only
        write_csv(pairs, rows)
        relevance = read_csv(rel)
        for row in relevance:
            if row['top10'] == '1':
                row['relevant'] = '1'
                row['annotator'] = name
                row['provenance'] = 'human'
        write_csv(rel, relevance)

    def second(self):
        p2 = self.root / 'second-pairs.csv'
        r2 = self.root / 'second-relevance.csv'
        p2.write_bytes(self.pairs.read_bytes())
        r2.write_bytes(self.relevance.read_bytes())
        return p2, r2

    def test_empty_packet_is_valid_but_blocked(self):
        sample = validate_packet(self.report, self.pairs, self.relevance)
        self.assertGreaterEqual(len(sample['pairs']), 100)
        result = audit(self.report, (self.pairs, self.relevance))
        self.assertEqual(result['status'], 'blocked_pending_review_or_adjudication')
        self.assertEqual(result['pair_labels_agreed_or_single'], 0)
        self.assertFalse(result['identity_verified'])

    def test_labeled_single_review_is_only_sample_metric_ready(self):
        self.mark(self.pairs, self.relevance, 'synthetic-A')
        result = audit(self.report, (self.pairs, self.relevance))
        self.assertEqual(result['status'], 'ready_for_sample_metrics')
        self.assertTrue(result['top10_fully_labeled'])
        self.assertTrue(result['human_provenance_self_declared_only'])
        self.assertFalse(result['identity_verified'])
        self.assertGreaterEqual(result['unique_articles_with_pair_labels'], 100)

    def test_second_review_conflict_and_distinct_identity(self):
        self.mark(self.pairs, self.relevance, 'synthetic-A')
        p2, r2 = self.second()
        rows = read_csv(p2)
        rows[0]['label'] = 'different_event'
        write_csv(p2, rows)
        # Same claimed identity cannot be called an independent review.
        with self.assertRaisesRegex(ValueError, 'distinct'):
            audit(self.report, (self.pairs, self.relevance), (p2, r2))
        rows = read_csv(p2)
        for row in rows:
            row['annotator'] = 'synthetic-B'
        write_csv(p2, rows)
        rel_rows = read_csv(r2)
        for row in rel_rows:
            if row['relevant']:
                row['annotator'] = 'synthetic-B'
        write_csv(r2, rel_rows)
        result = audit(self.report, (self.pairs, self.relevance), (p2, r2))
        self.assertEqual(result['status'], 'blocked_pending_review_or_adjudication')
        self.assertEqual(len(result['disagreements']), 1)
        rows = read_csv(p2)
        rows[0]['label'] = 'same_event'
        write_csv(p2, rows)
        resolved = audit(self.report, (self.pairs, self.relevance), (p2, r2))
        self.assertEqual(resolved['status'], 'ready_for_sample_metrics')
        self.assertEqual(resolved['mode'], 'two_reviewers')

    def test_wrong_report_rejected(self):
        rows = read_csv(self.pairs)
        rows[0]['report_id'] = 'some-other-report'
        write_csv(self.pairs, rows)
        with self.assertRaisesRegex(ValueError, 'another report'):
            validate_packet(self.report, self.pairs, self.relevance)

    def test_rejects_swapped_pair_and_extra_pair(self):
        rows = read_csv(self.pairs)
        rows[0]['left'] = self.report['items'][-1]['url']
        write_csv(self.pairs, rows)
        with self.assertRaisesRegex(ValueError, 'URL/id mismatch'):
            validate_packet(self.report, self.pairs, self.relevance)

    def test_tampered_candidate_metadata_rejected(self):
        rows = read_csv(self.pairs)
        rows[0]['candidate_kind'] = 'possible_event'
        write_csv(self.pairs, rows)
        with self.assertRaisesRegex(ValueError, 'metadata changed'):
            validate_packet(self.report, self.pairs, self.relevance)

    def test_tampered_top10_and_members_rejected(self):
        rows = read_csv(self.relevance)
        rows[0]['top10'] = '0'
        write_csv(self.relevance, rows)
        with self.assertRaisesRegex(ValueError, 'Top-10'):
            validate_packet(self.report, self.pairs, self.relevance)
        rows[0]['top10'] = '1'
        rows[0]['urls'] = 'https://example.org/swapped'
        write_csv(self.relevance, rows)
        with self.assertRaisesRegex(ValueError, 'members changed'):
            validate_packet(self.report, self.pairs, self.relevance)

    def test_invalid_human_provenance_rejected(self):
        rows = read_csv(self.pairs)
        rows[0]['label'] = 'same_event'
        rows[0]['annotator'] = 'tester'
        rows[0]['provenance'] = 'model'
        write_csv(self.pairs, rows)
        with self.assertRaisesRegex(ValueError, 'claimed human'):
            validate_packet(self.report, self.pairs, self.relevance)

    def test_true_digest_tampering_rejected(self):
        r = self.report.copy()
        r['revision'] = 'synthetic-revision'
        content = [r['revision'], [(x['url'], x['fingerprint']) for x in r['items']],
                   r['pairs'], r['scores']]
        r['report_id'] = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
        # Existing exported CSV belongs to previous report, but report itself is valid.
        with self.assertRaisesRegex(ValueError, 'Report content changed'):
            audit({**r, 'revision': 'changed'}, (self.pairs, self.relevance))


if __name__ == '__main__':
    unittest.main()
