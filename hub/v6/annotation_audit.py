"""Offline owner-side audit for V6 human review exports.

This is a data-integrity gate, NOT identity verification and NOT an accuracy
certification. It never infers a label, changes a report, approves a merge,
calls a model, or writes to the public website.
"""
import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from hub.v6.events import pair_id
from hub.v6.sampling import sample_pairs

PAIR_FIELDS = frozenset(('report_id', 'pair_id', 'left', 'right', 'label', 'annotator', 'provenance'))
REL_FIELDS = frozenset(('report_id', 'event_id', 'urls', 'relevant', 'annotator', 'provenance'))
PAIR_LABELS = frozenset(('', 'same_event', 'different_event'))
REL_LABELS = frozenset(('', '0', '1'))
MAX_CSV_BYTES = 5_000_000
MAX_REPORT_BYTES = 30_000_000


def _load_csv(path, required):
    path = Path(path)
    if path.stat().st_size > MAX_CSV_BYTES:
        raise ValueError('Annotation CSV too large')
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError('Missing or duplicated CSV headings')
        if required - set(reader.fieldnames):
            raise ValueError('Missing annotation CSV columns')
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError('Malformed CSV width')
    if len(rows) > 5000:
        raise ValueError('Unexpected annotation row count')
    return rows


def _report_digest(report):
    """Recompute the existing V6 report_id, without trusting the CSV alone."""
    content = [
        report['revision'],
        [(x['url'], x['fingerprint']) for x in report['items']],
        report['pairs'],
        report['scores'],
    ]
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def _check_report(report):
    if (not isinstance(report, dict) or not isinstance(report.get('items'), list)
            or not isinstance(report.get('pairs'), list)
            or not isinstance(report.get('scores'), list)
            or not isinstance(report.get('report_id'), str)):
        raise ValueError('Missing V6 report fields')
    urls = [x['url'] for x in report['items']]
    if len(set(urls)) != len(urls):
        raise ValueError('Duplicate report article URLs')
    ids = [s['event_id'] for s in report['scores']]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate scored events')
    if re.fullmatch(r'[0-9a-f]{64}', report['report_id']):
        if _report_digest(report) != report['report_id']:
            raise ValueError('Report content changed after report_id was created')
    if any(not set(s.get('members', [])) <= set(urls) for s in report['scores']):
        raise ValueError('Score contains foreign article URLs')


def _annotated(row, field, choices):
    value = row[field]
    if value not in choices:
        raise ValueError('Invalid human label value')
    who = row['annotator'].strip()
    provenance = row['provenance'].strip()
    if value:
        if not who or len(who) > 100 or provenance != 'human':
            raise ValueError('Labeled rows need a claimed human reviewer and provenance')
    elif who or provenance:
        raise ValueError('Blank labels cannot claim human review')
    return value


def validate_packet(report, pair_csv, relevance_csv):
    """Strictly bind both CSVs to a deterministically reconstructed packet."""
    _check_report(report)
    pairs = _load_csv(pair_csv, PAIR_FIELDS)
    relevance = _load_csv(relevance_csv, REL_FIELDS)
    items = {x['url']: x for x in report['items']}
    _, sample, manifest = sample_pairs(report['items'], report['pairs'])
    expected_pairs = {p['id']: p for p in sample}
    if len(pairs) != len(expected_pairs):
        raise ValueError('Pair packet has missing or extra rows')
    seen = set()
    for row in pairs:
        if row['report_id'] != report['report_id']:
            raise ValueError('Pair label belongs to another report')
        k = row['pair_id']
        if k in seen or k not in expected_pairs:
            raise ValueError('Unrecognized or duplicate pair in review packet')
        seen.add(k)
        p = expected_pairs[k]
        if ({row['left'], row['right']} != {p['left'], p['right']}
                or pair_id(row['left'], row['right']) != k):
            raise ValueError('Pair URL/id mismatch')
        for column, field in (('left_title', 'left'), ('right_title', 'right')):
            if column in row and row[column] != items[row[field]]['title']:
                raise ValueError('Annotation pair title does not match report')
        for column, source in (('sampling_stratum', 'sampling_stratum'),
                               ('candidate_kind', 'kind')):
            if column in row and row[column] != p[source]:
                raise ValueError('Review candidate metadata changed')
        _annotated(row, 'label', PAIR_LABELS)
    if len(set(row['pair_id'] for row in pairs)) != len(expected_pairs):
        raise ValueError('Missing sampled pairs')

    scored = {s['event_id']: s for s in report['scores']}
    selected = {u for p in sample for u in (p['left'], p['right'])}
    top_ids = {s['event_id'] for s in report['scores'][:10]}
    expected_rel = {s['event_id'] for s in report['scores']
                    if s['event_id'] in top_ids or set(s['members']) & selected}
    if len(relevance) != len(expected_rel):
        raise ValueError('Relevance packet has missing or extra rows')
    seen = set()
    for row in relevance:
        if row['report_id'] != report['report_id']:
            raise ValueError('Relevance label belongs to another report')
        key = row['event_id']
        if key in seen or key not in expected_rel:
            raise ValueError('Unexpected or duplicate relevance event')
        seen.add(key)
        score = scored[key]
        if row['urls'] != ' '.join(score['members']):
            raise ValueError('Relevance event members changed')
        if 'top10' in row and row['top10'] != ('1' if key in top_ids else '0'):
            raise ValueError('Top-10 audit marker changed')
        if 'title' in row and row['title'] != (
                items[score['members'][0]]['title'] if score['members'] else ''):
            raise ValueError('Relevance title does not match report')
        _annotated(row, 'relevant', REL_LABELS)
    return {'pairs': pairs, 'relevance': relevance, 'manifest': manifest,
            'top10': top_ids}


def audit(report, primary, secondary=None):
    """Report review coverage; require a separate, named adjudication for conflict.

    Output never certifies human identity. When two independent reviewers
    agree, that is observed agreement between two CSV claims, not an
    authenticated statement about who made the judgments.
    """
    _check_report(report)
    p1 = validate_packet(report, primary[0], primary[1])
    p2 = validate_packet(report, secondary[0], secondary[1]) if secondary else None
    disagreements = []
    distinct = set()
    label_count = Counter()
    scored_a = []
    for name, field, key in [('pairs', 'label', 'pair_id'),
                              ('relevance', 'relevant', 'event_id')]:
        rows_a = {r[key]: r for r in p1[name]}
        rows_b = {r[key]: r for r in p2[name]} if p2 else {}
        for identifier, left in rows_a.items():
            l = left[field]
            if not l:
                continue
            if p2:
                right = rows_b[identifier]
                r = right[field]
                if not r:
                    continue
                if left['annotator'].strip().casefold() == right['annotator'].strip().casefold():
                    raise ValueError('Dual review must use distinct reviewer identifiers')
                if l != r:
                    disagreements.append({'kind': name, 'id': identifier,
                                          'first': l, 'second': r})
                    continue
            label_count[name] += 1
            if name == 'pairs':
                distinct.update((left['left'], left['right']))
                scored_a.append(l)
    top_ids = p1['top10']
    ready_top = all(
        any(r['event_id'] == key and r['relevant'] and
            (not p2 or next((b['relevant'] == r['relevant']
                             and b['annotator'].strip().casefold() != r['annotator'].strip().casefold()
                             for b in p2['relevance'] if b['event_id'] == key), False))
            for r in p1['relevance'])
        for key in top_ids
    )
    eligible = (label_count['pairs'] >= 100 and len(distinct) >= 100
                and len(set(scored_a)) >= 2 and ready_top
                and not disagreements and p1['manifest']['proposal_coverage_complete'])
    return {
        'status': 'ready_for_sample_metrics' if eligible else 'blocked_pending_review_or_adjudication',
        'report_id': report['report_id'],
        'mode': 'two_reviewers' if p2 else 'single_reviewer',
        'identity_verified': False,
        'human_provenance_self_declared_only': True,
        'pair_labels_agreed_or_single': label_count['pairs'],
        'relevance_labels_agreed_or_single': label_count['relevance'],
        'unique_articles_with_pair_labels': len(distinct),
        'pair_positive': scored_a.count('same_event'),
        'pair_negative': scored_a.count('different_event'),
        'top10_fully_labeled': ready_top,
        'proposal_coverage_complete': p1['manifest']['proposal_coverage_complete'],
        'sampling_strata': p1['manifest']['strata'],
        'disagreements': disagreements,
        'warning': 'Readiness is for sample-only evaluation. This does not prove reviewer identity, whole-corpus recall or production quality.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True)
    parser.add_argument('--pairs', required=True)
    parser.add_argument('--relevance', required=True)
    parser.add_argument('--second-pairs')
    parser.add_argument('--second-relevance')
    parser.add_argument('--out', required=True)
    a = parser.parse_args()
    if bool(a.second_pairs) != bool(a.second_relevance):
        parser.error('Both second reviewer files are required')
    report_path = Path(a.report)
    if report_path.stat().st_size > MAX_REPORT_BYTES:
        raise SystemExit('Report JSON too large')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    result = audit(report, (a.pairs, a.relevance),
                   (a.second_pairs, a.second_relevance) if a.second_pairs else None)
    output = Path(a.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SystemExit('Refusing to overwrite an existing audit; use a new output')
    # Never write data to a project source directory in the public repository.
    tmp = output.with_name(output.name + '.tmp')
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(output)
    print(json.dumps({k: result[k] for k in
                      ('status', 'mode', 'pair_labels_agreed_or_single',
                       'top10_fully_labeled', 'proposal_coverage_complete')}, ensure_ascii=False))
    raise SystemExit(0 if result['status'] == 'ready_for_sample_metrics' else 2)


if __name__ == '__main__':
    main()
