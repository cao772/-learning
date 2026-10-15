"""Bounded, explainable personalization over already-imported ranked items.

Only the owner's explicit feedback/saved/active-research actions inform
preference hints. No model calls, browsing history, tracking or data sharing.
"""
from collections import Counter

FEEDBACK = {"已用上":2,"值得深读":2,"有趣但暂不用":0,
            "现在用不上":-2,"重复":-2,"证据不好":-3}
ACTIVE = {"待精读","待复现","可能用于项目"}


def source_key(item):
    source=item.get("source")
    return source.strip().casefold() if isinstance(source,str) and source.strip() else "来源未知"


def bounded(total):
    # Multiple explicit actions are required before affecting unrelated stories.
    if abs(total)<2:return 0
    return max(-3,min(3, (abs(total)//2) * (1 if total>0 else -1)))


def preference_signals(rows, research=None):
    """Only explicit owner signals; manual category correction is not approval."""
    research=research or {}
    sources=Counter();categories=Counter();acted=0
    for row in rows:
        item=row.get("item") or {}
        personal=item.get("personal") or {}
        feedback=personal.get("feedback")
        signal=FEEDBACK.get(feedback,0)
        if personal.get("saved"):signal+=1
        record=research.get(str(item.get("id") or ""))
        if isinstance(record,dict) and record.get("decision") in ACTIVE:signal+=1
        if not signal:continue
        acted+=1
        sources[source_key(item)]+=signal
        categories[row.get("category") or "other"]+=signal
    return {
        "source":{key:bounded(value) for key,value in sources.items()},
        "category":{key:bounded(value) for key,value in categories.items()},
        "explicit_items":acted
    }


def balance_recommendations(rows, research=None, limit=80, top_window=12,
                            per_source=3,per_category=4):
    """Soft diversity among first N items; never remove items or upgrade status.

    Stable selection: first chooses a high-scoring item satisfying diversity
    limits, then gracefully fills with remaining items if no alternative.
    """
    signals=preference_signals(rows,research)
    candidates=[]
    for original in rows:
        row={**original,"reasons":list(original.get("reasons") or [])}
        score=int(row.get("score") or 0)
        cat=row.get("category") or "other"
        src=source_key(row.get("item") or {})
        boost=max(-4,min(4,signals["category"].get(cat,0)+signals["source"].get(src,0)))
        row["base_score"]=score
        row["score"]=max(0,score+boost)
        row["recommendation_adjustment"]=boost
        if boost:
            row["reasons"].append("历史显式反馈调整了阅读排序（不是内容质量评分）")
        candidates.append(row)
    # Stable sort keeps existing recency tie break from original ranking.
    candidates.sort(key=lambda row:-row["score"])
    selected=[];remaining=list(candidates)
    src_counts=Counter();cat_counts=Counter()
    while remaining and len(selected)<min(top_window,limit):
        eligible=None
        for i,row in enumerate(remaining):
            src=source_key(row.get("item") or {})
            cat=row.get("category") or "other"
            if src_counts[src]<per_source and cat_counts[cat]<per_category:
                eligible=i;break
        if eligible is None:
            eligible=0
        entry=remaining.pop(eligible)
        src_counts[source_key(entry.get("item") or {})]+=1
        cat_counts[entry.get("category") or "other"]+=1
        if eligible>0:
            entry["reasons"].append("为减少单一来源或类别霸屏，调整了展示顺序")
        selected.append(entry)
    return {
        "ranking":(selected+remaining)[:limit],
        "meta":{
            "method":"明确反馈、收藏、实际研究计划的有界调整；前排来源和分类柔性分散",
            "explicit_feedback_items":signals["explicit_items"],
            "top_window":min(top_window,len(selected)),
            "model_calls":0,
            "not_quality_score":True
        }
    }
