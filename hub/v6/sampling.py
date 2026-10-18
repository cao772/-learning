"""Deterministic *review sampling*, not pseudo human labels or a quality score.

Candidate proposals and hard counterexamples precede background coverage. An
independent title-anchor retrieval route lets reviewers inspect potential
false negatives absent from the embedding candidate list.
"""
import itertools
import random
from collections import Counter, defaultdict

from hub.content_category import classify_item
from hub.v6.events import pair_id, publication, tokens

PROPOSALS = frozenset(('possible_event', 'possible_reprint'))
HARD_BLOCKERS = frozenset((
    'different_paper_identifiers', 'different_repository_identifiers',
    'conflicting_versions', 'different_content_types', 'outside_72h_window',
))
COMMON = frozenset((
    'using', 'model', 'models', 'agent', 'agents', 'learning', 'towards',
    'research', 'results', 'large', 'language', 'system', 'systems', 'open',
    'source', 'paper', 'based', 'with', 'from', 'this', 'that', 'new',
))


def _alternate_candidates(items, known, limit=1200):
    """Independent rare-title-token retrieval, *not* embedding retrieval."""
    sources = defaultdict(list)
    meta = {}
    for x in items:
        # Avoid one-character CJK tokens: common words create false anchors.
        terms = {t for t in tokens(x.get('title', ''))
                 if len(t) >= 3 and t not in COMMON}
        meta[x['url']] = (classify_item(x)['category'], publication(x))
        for term in sorted(terms):
            sources[term].append(x['url'])
    seen = set()
    out = []
    for term in sorted(sources, key=lambda t: (len(sources[t]), t)):
        urls = sorted(set(sources[term]))
        if not 2 <= len(urls) <= 24:
            continue
        for a, b in itertools.combinations(urls, 2):
            key = pair_id(a, b)
            if key in seen or key in known:
                continue
            ca, ta = meta[a]
            cb, tb = meta[b]
            if ca != cb or ta is None or tb is None:
                continue
            if abs((ta - tb).total_seconds()) > 72 * 3600:
                continue
            seen.add(key)
            out.append({'id': key, 'left': a, 'right': b, 'kind': 'unproposed',
                        'anchor': term})
            if len(out) >= limit:
                return out
    return out


def sample_pairs(items, proposals, article_limit=160, pair_limit=160, seed=20261018):
    """Return (articles, pairs, manifest) with all proposed pairs first.

    Pair strata describe the *sampling method* only. They must never be used
    as ground-truth same/different-event labels. At most 160 articles and 160
    pairs by default. If the proposed population exceeds the budget, report
    shortfall and forbid completeness claims.
    """
    by_url = {x['url']: x for x in items}
    if len(by_url) != len(items):
        raise ValueError('Duplicate URLs in sample input')
    if article_limit < 2 or pair_limit < 1:
        raise ValueError('Sampling budgets must be positive')
    target = min(article_limit, len(items))
    picked = []
    articles = set()
    ids = set()

    def add(row, stratum):
        if len(picked) >= pair_limit:
            return False
        a, b = row['left'], row['right']
        if a == b or a not in by_url or b not in by_url:
            return False
        key = pair_id(a, b)
        if key in ids:
            return False
        new = len({a, b} - articles)
        if len(articles) + new > target:
            return False
        # Reserve enough pair slots to cover the promised article count.
        remaining_slots = pair_limit - len(picked) - 1
        if max(0, target - len(articles) - new) > 2 * remaining_slots:
            return False
        ids.add(key)
        articles.update((a, b))
        picked.append({**row, 'id': key, 'sampling_stratum': stratum})
        return True

    proposed = sorted(
        (p for p in proposals if p['kind'] in PROPOSALS),
        key=lambda p: (p['kind'] != 'possible_event', -p.get('cosine', 0), p['id']))
    for row in proposed:
        # Proposed pairs always take priority over unproposed material.
        if len(picked) >= min(40, pair_limit):
            break
        add(row, 'proposed')
    hard = sorted(
        (p for p in proposals if p.get('kind') == 'same_topic'
         and HARD_BLOCKERS.intersection(p.get('blockers') or [])),
        key=lambda p: (-p.get('cosine', 0), p['id']))
    for row in hard:
        if sum(p['sampling_stratum'] == 'blocked_high_similarity' for p in picked) >= min(40, pair_limit // 3):
            break
        add(row, 'blocked_high_similarity')
    known = {p['id'] for p in proposals}
    alternate = _alternate_candidates(items, known)
    for row in alternate:
        if sum(p['sampling_stratum'] == 'alternate_retrieval' for p in picked) >= min(30, pair_limit // 4):
            break
        add(row, 'alternate_retrieval')

    # Diverse category coverage first, even when no model pair is proposed.
    # Input URL ordering must not change the packet.
    buckets = defaultdict(list)
    for x in sorted(items, key=lambda item: item['url']):
        buckets[classify_item(x)['category']].append(x['url'])
    order = []
    while any(buckets.values()):
        for category in sorted(buckets):
            if buckets[category]:
                order.append(buckets[category].pop(0))
    missing = [u for u in order if u not in articles]
    while missing and len(articles) < target and len(picked) < pair_limit:
        a = missing.pop(0)
        if missing:
            b = missing.pop(0)
        else:
            b = next((u for u in sorted(articles) if pair_id(a, u) not in ids), None)
        if b is None:
            raise ValueError('Cannot cover a singleton article')
        if not add({'left': a, 'right': b, 'kind': 'unproposed'}, 'coverage_unlabeled'):
            raise ValueError('Sampling budget could not cover the articles')

    # Complete the pair budget without adding new articles.
    # Deterministic seed for auditable reproducibility, not a fake negative label.
    rng = random.Random(seed)
    eligible = sorted(articles)
    max_pairs = len(eligible) * (len(eligible) - 1) // 2
    if len(picked) < min(pair_limit, max_pairs):
        pool = list(itertools.combinations(eligible, 2))
        rng.shuffle(pool)
        for a, b in pool:
            if len(picked) >= pair_limit:
                break
            add({'left': a, 'right': b, 'kind': 'unproposed'}, 'background_unlabeled')

    counts = dict(sorted(Counter(p['sampling_stratum'] for p in picked).items()))
    manifest = {
        'method': 'proposed + blocked + independent title retrieval + category coverage + seeded background',
        'seed': seed,
        'articles': len(articles),
        'pairs': len(picked),
        'proposal_population': len(proposed),
        'proposal_included': sum(p['sampling_stratum'] == 'proposed' for p in picked),
        'proposal_coverage_complete': len(proposed) == sum(
            p['sampling_stratum'] == 'proposed' for p in picked),
        'alternate_retrieval_population': len(alternate),
        'strata': counts,
        'warning': 'All pairs are unlabeled. Human judgment is required; sampled recall is not corpus recall.',
    }
    return [by_url[u] for u in sorted(articles)], picked, manifest
