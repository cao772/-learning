"""Deterministic offline candidate links, never automatic semantic merges."""
import datetime as dt
import hashlib
import itertools
import re
import unicodedata
from urllib.parse import urlsplit
from hub.content_category import classify_item

RULE_VERSION = 'v6-events-0.2-experimental'
WINDOW_HOURS = 72


def tokens(value):
    value = unicodedata.normalize('NFKC', value).casefold()
    return re.findall(r'[a-z0-9]+|[\u4e00-\u9fff]', value)


def shingles(value):
    words = tokens(value)
    return {' '.join(words[i:i+3]) for i in range(max(0,len(words)-2))}


def minhash(parts, size=64):
    if not parts:
        return None
    # Stable seeded permutations; no process-randomized Python hash().
    prime = (1 << 61) - 1
    values = [int.from_bytes(hashlib.sha256(x.encode()).digest()[:8], 'big') % prime for x in parts]
    return tuple(min(((i*2+1)*x + i*i*104729) % prime for x in values) for i in range(1,size+1))


def jaccard(a,b):
    return len(a & b) / len(a | b) if a and b else 0.0


def publication(item):
    value = item.get('published_at')
    try:
        d = dt.datetime.fromisoformat(value.replace('Z','+00:00'))
        return d if d.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def anchors(item):
    title = item.get('title','')
    # Conservative named-token proxy, not an NER claim. Generic AI terms excluded.
    generic = {'a','an','the','we','ai','llm','llms','agent','agents','learning','model','models',
               'towards','with','for','from','how','using','large','language','new','via',
               'deep','based','multi','on','in','to','of','and','is','can','by','open','research'}
    names = {x.casefold() for x in re.findall(r'\b[A-Z][A-Za-z0-9_-]{2,}\b', title)}
    names |= {x.casefold() for x in re.findall(r'\b[a-zA-Z]+[-_]?\d+(?:\.\d+)*\b', title)}
    for name in ('OpenAI','Anthropic','Claude','Gemini','DeepSeek','Qwen','Llama','PilotDeck','GPT'):
        if name.casefold() in title.casefold():names.add(name.casefold())
    return names - generic


def versions(item):
    # Version numbers only; dates, percentages and benchmark figures are not versions.
    return set(re.findall(r'(?<!\d)\d+\.\d+(?:\.\d+)?(?!\d)', item.get('title','')))


def pair_id(a,b):
    return hashlib.sha256('\n'.join(sorted((a,b))).encode()).hexdigest()[:24]


def candidates(items, similarities):
    prepared=[]
    for item in items:
        parts=shingles(item.get('title','')+' '+item.get('summary',''))
        prepared.append((parts,minhash(parts),anchors(item),publication(item),classify_item(item)['category']))
    out=[]
    for i,j in itertools.combinations(range(len(items)),2):
        a,b=items[i],items[j];pa,ma,ea,ta,ca=prepared[i];pb,mb,eb,tb,cb=prepared[j]
        cosine=float(similarities[i][j])
        mh=sum(x==y for x,y in zip(ma,mb))/len(ma) if ma and mb else 0.0
        # MinHash is a candidate screen; exact shingle overlap verifies retransmission.
        overlap=jaccard(pa,pb) if mh>=0.55 else 0.0
        same_link=a['url']==b['url']
        if not same_link and cosine<0.62 and overlap<0.78:continue
        shared=sorted(ea & eb)
        hours=abs((ta-tb).total_seconds())/3600 if ta and tb else None
        blockers=[]
        if ca!=cb:blockers.append('different_content_types')
        # Two arXiv works can be extremely similar follow-up research, yet are
        # different publication events. Version suffixes of one work are allowed.
        ua,ub=urlsplit(a['url']),urlsplit(b['url'])
        if ua.hostname in ('arxiv.org','www.arxiv.org') and ub.hostname in ('arxiv.org','www.arxiv.org'):
            if re.sub(r'v[0-9]+$','',ua.path)!=re.sub(r'v[0-9]+$','',ub.path):
                blockers.append('different_paper_identifiers')
        if ca==cb=='code' and ua.hostname==ub.hostname=='github.com' and ua.path.lower()!=ub.path.lower():
            blockers.append('different_repository_identifiers')
        if hours is None:blockers.append('unknown_publication_time')
        elif hours>WINDOW_HOURS:blockers.append('outside_72h_window')
        va,vb=versions(a),versions(b)
        if va and vb and va.isdisjoint(vb):blockers.append('conflicting_versions')
        if same_link:kind='same_url'
        elif blockers:kind='same_topic'
        elif overlap>=0.78 and len(pa)>=15 and len(pb)>=15:kind='possible_reprint'
        elif cosine>=0.82 and shared:kind='possible_event'
        else:kind='same_topic'
        out.append({'id':pair_id(a['url'],b['url']),'left':a['url'],'right':b['url'],
                    'kind':kind,'cosine':round(cosine,6),'minhash':round(mh,6),'jaccard':round(overlap,6),
                    'shared_anchors':shared,'hours_apart':round(hours,2) if hours is not None else None,
                    'blockers':blockers,'review_status':'pending' if kind in ('possible_reprint','possible_event') else 'not_mergeable',
                    'rule_version':RULE_VERSION})
    return sorted(out,key=lambda p:p['id'])


def approved_groups(items,pairs,reviews):
    """Review decisions are fingerprint-bound; require complete-link confirmation.

    A-B and B-C approval does not silently approve A-C. Rejected pairs cannot be
    bypassed through a third item. This deliberately sacrifices recall for safety.
    """
    items=sorted(items,key=lambda x:x['url']); by_url={x['url']:x for x in items}
    approved=set()
    for p in pairs:
        r=reviews.get(p['id'],{})
        if p['kind'] not in ('possible_reprint','possible_event'):continue
        if (r.get('decision')=='merge' and r.get('left_fingerprint')==by_url[p['left']]['fingerprint']
            and r.get('right_fingerprint')==by_url[p['right']]['fingerprint']):
            approved.add(frozenset((p['left'],p['right'])))
    groups=[]
    for item in items:
        for group in groups:
            if all(frozenset((item['url'],other)) in approved for other in group):
                group.append(item['url']);break
        else:groups.append([item['url']])
    return groups
