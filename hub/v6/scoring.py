"""Public experimental attention signals; no private parameters accepted."""
import math
from urllib.parse import urlsplit
from hub.content_category import classify_item
from hub.v6.events import publication, shingles, jaccard

VERSION='v6-public-0.2-uncalibrated'
# importance/novelty remain unknown until evidence or calibrated human assessment.
WEIGHTS={
 'agent':(.20,.20,.25,.25,.10), 'paper':(.20,.25,.35,.10,.10),
 'code':(.15,.15,.25,.35,.10), 'product':(.20,.15,.20,.30,.15),
 'tutorial':(.10,.15,.25,.40,.10), 'architecture':(.15,.15,.30,.30,.10),
 'science':(.20,.25,.35,.10,.10), 'industry':(.25,.20,.25,.10,.20),
 'other':(.20,.20,.30,.20,.10)}
AXES=('importance','novelty','evidence','practical_value','diffusion')
AGGREGATORS=('bestblogs.dev','aihot.news','quaily.com','arxiv.org')


def origin_group(url):
    host=(urlsplit(url).hostname or '').lower().removeprefix('www.')
    if any(host==a or host.endswith('.'+a) for a in AGGREGATORS):return None
    # Coarse domain grouping is a conservative independence LOWER BOUND, not proof.
    if host=='github.com':return 'github.com'  # repo owners aren't verified independent publishers
    return '.'.join(host.split('.')[-2:]) or None


def score(items,as_of):
    """Use original publication ONLY for freshness; never replay/fetch/change times."""
    # Cross-domain near-identical text may be syndication. Count it once rather
    # than treating copies as independent corroboration. Unknown aggregators=0.
    representatives=[]
    for x in sorted(items,key=lambda row:row['url']):
        parts=shingles(x.get('title','')+' '+x.get('summary',''))
        if not any(jaccard(parts,other)>=.78 for other in representatives):
            representatives.append(parts)
    domains={origin_group(x['url']) for x in items}-{None}
    independent=min(len(domains),len(representatives))
    days=[]
    for x in items:
        d=publication(x)
        if d and d<=as_of:days.append((as_of-d).total_seconds()/86400)
    freshness=math.exp(-math.log(2)*min(days)/2) if days else 0.0
    heat=round(100*(1-math.exp(-independent/3))*freshness,4)
    # Deterministic primary member; categories are required equal before merge.
    primary=min(items,key=lambda x:x['url']);cat=classify_item(primary)['category']
    summary=primary.get('summary','');title=primary.get('title','')
    evidence=.25 if origin_group(primary['url']) else .10
    if cat=='paper' and 'arxiv.org' in primary['url']:evidence=.25
    practical=.30 if summary else 0.0
    if cat in ('code','tutorial','architecture') and summary:practical=.45
    axes={'importance':None,'novelty':None,'evidence':evidence,
          'practical_value':practical,'diffusion':min(1,independent/4)*freshness}
    weighted=sum(WEIGHTS[cat][i]*(axes[k] or 0) for i,k in enumerate(AXES))
    return {'category':cat,'score':round(100*weighted,4),'heat':heat,'axes':axes,
            'weights':dict(zip(AXES,WEIGHTS[cat])),'independent_origin_lower_bound':independent,
            'freshness':round(freshness,6),'as_of':as_of.isoformat(),'rule_version':VERSION,
            'missing':['importance_assessment','novelty_assessment','full_text_verification','source_independence_verification']+
                      (['publication_time'] if not days else [])+
                      (['runtime_or_replication_evidence'] if cat in ('paper','code') else []),
            'explanation':['未校准的元数据注意力分，不代表内容质量或事实正确性。',
                           '重要性与信息增量未知按0贡献，不用标题词或星数伪造评审。',
                           '热度仅使用原文发表时间和保守来源下界，采集/回放时间不参与。',
                           '摘要存在仅是阅读线索；论文全文、项目运行、来源独立性均未核验。'],
            'evidence_urls':sorted(x['url'] for x in items),'verification_status':'candidate'}
