"""Back-end only regression: review packet coverage and honest metric labels."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from hub.v6.events import pair_id
from hub.v6.sampling import sample_pairs
from hub.v6.offline import packet
from hub.v6.evaluate import evaluate


class SamplingTests(unittest.TestCase):
    @staticmethod
    def items(n=180):
        data = [{
            'url': 'https://example.org/story-%03d' % i,
            'title': 'Research Evidence Analysis %03d' % i,
            'summary': 'Unverified report requiring human review',
            'published_at': '2026-10-18T08:00:00+00:00',
            'fingerprint': 'fp%d' % i,
        } for i in range(n)]
        for i in (9, 10):
            data[i]['title'] = 'ProjectZephyr Launch %d' % i
        return data

    def test_all_proposals_selected_with_hard_cases_and_independent_probes(self):
        items = self.items()
        def relation(i, j, kind, blockers=None):
            return {'id': pair_id(items[i]['url'], items[j]['url']),
                    'left': items[i]['url'], 'right': items[j]['url'],
                    'kind': kind, 'cosine': .92, 'blockers': blockers or []}
        pairs = [relation(0, 1, 'possible_event'),
                 relation(4, 5, 'possible_reprint'),
                 relation(2, 3, 'same_topic', ['different_paper_identifiers'])]
        articles, selected, manifest = sample_pairs(items, pairs)
        self.assertEqual((len(articles), len(selected)), (160, 160))
        self.assertEqual(manifest['proposal_population'], 2)
        self.assertEqual(manifest['proposal_included'], 2)
        self.assertTrue(manifest['proposal_coverage_complete'])
        strata = {row['id']: row['sampling_stratum'] for row in selected}
        for pair in pairs[:2]:
            self.assertEqual(strata[pair['id']], 'proposed')
        self.assertEqual(strata[pairs[2]['id']], 'blocked_high_similarity')
        alternate = pair_id(items[9]['url'], items[10]['url'])
        self.assertEqual(strata[alternate], 'alternate_retrieval')
        reversed_docs, reversed_pairs, reversed_manifest = sample_pairs(items[::-1], pairs[::-1])
        self.assertEqual(articles, reversed_docs)
        self.assertEqual(selected, reversed_pairs)
        self.assertEqual(manifest, reversed_manifest)

    def test_packet_contains_top10_relevance_and_unlabeled_strata(self):
        items = self.items(160)
        report = {'report_id': 'r1', 'items': items, 'pairs': [],
                  'scores': [{'event_id': 'e%d' % i, 'members': [items[i]['url']]}
                             for i in range(160)]}
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            packet(report, out)
            with (out / 'pair-labels.csv').open() as file:
                pairs = list(csv.DictReader(file))
            with (out / 'relevance-labels.csv').open() as file:
                rel = list(csv.DictReader(file))
            manifest = json.loads((out / 'annotation-sample.json').read_text())['sampling']
            self.assertEqual(len(pairs), 160)
            self.assertEqual(len({u for p in pairs for u in (p['left'], p['right'])}), 160)
            self.assertEqual(manifest['articles'], 160)
            self.assertTrue(all(row['sampling_stratum'] for row in pairs))
            self.assertTrue(all(row['label'] == '' for row in pairs))
            self.assertEqual([r['event_id'] for r in rel[:10]], ['e%d' % i for i in range(10)])
            self.assertTrue(all(r['top10'] == '1' for r in rel[:10]))

    def test_overbudget_proposals_do_not_claim_full_coverage(self):
        items = self.items(180)
        proposed = []
        for i in range(70):
            a, b = items[i * 2]['url'], items[i * 2 + 1]['url']
            proposed.append({'id': pair_id(a, b), 'left': a, 'right': b,
                             'kind': 'possible_event', 'cosine': .9})
        _, _, manifest = sample_pairs(items, proposed)
        self.assertFalse(manifest['proposal_coverage_complete'])
        self.assertLess(manifest['proposal_included'], manifest['proposal_population'])


class EvaluationMetricTests(unittest.TestCase):
    def test_false_discovery_is_not_approved_merge_error_rate(self):
        items = [{'url': 'https://example.org/%d' % i} for i in range(100)]
        rows, proposals = [], []
        for i in range(50):
            a = items[i * 2]['url']
            b = items[i * 2 + 1]['url']
            key = pair_id(a, b)
            if i < 10:
                proposals.append({'id': key, 'kind': 'possible_event'})
            label = 'same_event' if i < 5 or 10 <= i < 15 else 'different_event'
            rows.append({'report_id': 'r', 'pair_id': key, 'left': a, 'right': b,
                         'label': label, 'annotator': 'reviewer-A', 'provenance': 'human',
                         'sampling_stratum': 'proposed' if i < 10 else 'background_unlabeled'})
        # Add 50 separately labeled pairs covering the same 100 articles.
        for i in range(50):
            a = items[i]['url']
            b = items[i + 50]['url']
            rows.append({'report_id': 'r', 'pair_id': pair_id(a, b),
                         'left': a, 'right': b, 'label': 'different_event',
                         'annotator': 'reviewer-A', 'provenance': 'human',
                         'sampling_stratum': 'background_unlabeled'})
        report = {'report_id': 'r', 'items': items, 'pairs': proposals,
                  'scores': [{'event_id': 'e%d' % i} for i in range(10)]}
        with tempfile.TemporaryDirectory() as folder:
            labels = Path(folder) / 'pairs.csv'
            relevance = Path(folder) / 'relevance.csv'
            with labels.open('w', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            with relevance.open('w', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=['report_id', 'event_id',
                                                          'relevant', 'annotator', 'provenance'])
                writer.writeheader()
                writer.writerows([{'report_id': 'r', 'event_id': 'e%d' % i,
                                  'relevant': '1', 'annotator': 'reviewer-A',
                                  'provenance': 'human'} for i in range(10)])
            result = evaluate(report, labels, relevance)
        self.assertEqual(result['status'], 'evaluated_on_labeled_sample')
        self.assertEqual(result['precision'], .5)
        self.assertEqual(result['recall'], .5)
        self.assertEqual(result['proposal_false_discovery_rate'], .5)
        self.assertIsNone(result['false_merge_rate'])
        self.assertIsNone(result['approved_merge_error_rate'])
        self.assertEqual(result['p_at_10'], 1.0)
        self.assertEqual(result['sampling_strata']['proposed']['reviewed'], 10)


if __name__ == '__main__':
    unittest.main()
