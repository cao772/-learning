"""Conservative, explainable connections between already imported intelligence items.

No web fetch, model call, guessed metrics, external profiles, or private-note publication.
Related titles are *suggestions for review*, not deduplicated facts.
"""
import hashlib
import re
import unicodedata
from urllib.parse import urlsplit

from hub.discovery import canonical_link


def classify_source(url):
    """Determine which human evaluation checklist to show, not quality or success."""
    try:
        parsed = urlsplit(url or "")
        host = (parsed.hostname or "").casefold()
        parts = [x for x in parsed.path.split("/") if x]
    except ValueError:
        return "general"
    if host in {"github.com", "www.github.com"} and len(parts) >= 2 and parts[0] not in {
            "topics", "trending", "features", "settings", "orgs", "marketplace"}:
        return "repository"
    if host in {"arxiv.org", "www.arxiv.org", "doi.org", "www.doi.org", "openreview.net", "www.openreview.net"}:
        return "paper"
    if host.endswith(".nature.com") or host in {"nature.com", "www.nature.com", "science.org", "www.science.org"}:
        return "paper"
    return "general"


CHECKLISTS = {
    "repository": [
        "确认源码和许可证（是否允许当前使用场景）",
        "核对最近维护、Issue 状态与关键依赖",
        "安装运行一个最小可复现实例",
        "与已有方案做同场景比较，记录适配工作量",
    ],
    "paper": [
        "核对论文原文、作者与具体主张",
        "识别实验数据、基线和边界条件",
        "找到代码/数据开放情况，挑选可复现部分",
        "记录与当前研究/项目的联系及反例",
    ],
    "general": [
        "读原文并区分事实、观点和转载",
        "核对发布时间、来源和支撑证据",
        "总结一个具体可验证的问题",
        "小规模试验并记录是否值得进一步学习",
    ],
}


def _canonical(value):
    try:
        return canonical_link(value)
    except (ValueError, TypeError, AttributeError):
        return None


def _title_key(value):
    if not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized)


def _provenance(row, origin):
    return {
        "id": row.get("id"), "origin": origin, "title": row.get("title") or "",
        "source": row.get("source") or "来源未知", "url": row.get("url") or "",
        "published_at": row.get("published_at"),
        "verification_status": row.get("verification_status") or "candidate",
    }


def connect_sources(ranking, captures, max_groups=20):
    """Return strictly same-URL groups and weaker same-title prompts separately.

    Captured bookmarks remain PRIVATE. Does not merge, upgrade or publish items.
    """
    entries = []
    for record in ranking:
        if isinstance(record, dict) and isinstance(record.get("item"), dict):
            entries.append(_provenance(record["item"], "feed"))
    for captured in captures:
        if isinstance(captured, dict):
            entries.append(_provenance(captured, "private_capture"))

    by_url = {}
    by_title = {}
    for entry in entries:
        url = _canonical(entry["url"])
        if not url:
            continue
        by_url.setdefault(url, []).append(entry)
        title = _title_key(entry["title"])
        # Long, exactly normalized titles may indicate related reports; not proof.
        if len(title) >= 18:
            by_title.setdefault(title, []).append((url, entry))

    groups = []
    for url, members in by_url.items():
        # The same ID is not independent coverage; entries may be from one RSS feed.
        ids = set()
        unique = []
        for member in members:
            marker = (member["origin"], member["id"])
            if marker not in ids:
                unique.append(member)
                ids.add(marker)
        if len(unique) >= 2:
            groups.append({
                "key": hashlib.sha256(url.encode()).hexdigest()[:16],
                "basis": "同一规范链接，非独立来源证明",
                "url": url, "members": unique[:12],
            })
    groups.sort(key=lambda g: (-len(g["members"]), g["url"]))

    maybes = []
    for title, pairs in by_title.items():
        distinct_urls = {url for url, _ in pairs}
        if len(distinct_urls) < 2:
            continue
        by_url_only = {}
        for url, item in pairs:
            by_url_only.setdefault(url, item)
        maybes.append({
            "key": hashlib.sha256(title.encode()).hexdigest()[:16],
            "basis": "标题一致，需核实是否为同一事件或转载",
            "members": list(by_url_only.values())[:8],
        })
    maybes.sort(key=lambda g: (-len(g["members"]), g["key"]))
    return {"same_link": groups[:max_groups], "similar_title": maybes[:max_groups]}


def research_brief(item):
    """Unverified checklist seed; never claim a repo was run or a paper reproduced."""
    kind = classify_source(item.get("url", ""))
    return {
        "kind": kind,
        "checklist": CHECKLISTS[kind],
        "metrics": {
            "github_stars": None, "license": None, "last_commit": None,
            "paper_fulltext_read": None, "reproduced": None,
        },
        "evidence_level": "待验证",
    }


def interest_collections(ranking, max_groups=12):
    """Cluster by *stated matching interests*, not by claimed semantic equivalence.

    Mixed-source results may be useful for exploring a topic, but never
    constitute corroborating or independent support for a factual assertion.
    """
    from hub.discovery import INTERESTS
    from hub.content_category import LABELS
    buckets = {}
    for record in ranking:
        if not isinstance(record, dict) or not isinstance(record.get("item"), dict):
            continue
        item = record["item"]
        primary = record.get("category")
        for tag in record.get("match_keys", []):
            if not isinstance(tag, str) or (tag not in INTERESTS and not tag.startswith("custom:")):
                continue
            # Repo and paper formats have their own browsing sections; topic
            # comparisons also stay within one PRIMARY content category.
            if tag in ("open_source", "research"):
                continue
            bucket = buckets.setdefault((tag,primary), [])
            key = str(item.get("id", ""))
            if key and all(str(other.get("id")) != key for other in bucket):
                bucket.append(item)
    groups = []
    for (tag, primary), entries in buckets.items():
        if len(entries) < 2:
            continue
        sources = {str(x.get("source") or "未知") for x in entries}
        if len(sources) < 2:
            continue
        topic = INTERESTS[tag]["label"] if tag in INTERESTS else tag.removeprefix("custom:")
        groups.append({
            "tag": tag, "category": primary,
            "label": topic + (" · " + LABELS[primary] if primary in LABELS else ""),
            "basis": "同一主分类内关键词命中兴趣，不代表结论相同；论文、代码项目等不得混编",
            "source_count": len(sources),
            "members": [_provenance(item, "feed") for item in entries[:12]],
        })
    return sorted(groups, key=lambda x: (-x["source_count"], -len(x["members"]), x["label"]))[:max_groups]


def suggested_research(ranking, recorded_ids, limit=8):
    """Non-persistent learning prompts only; never mark tasks performed."""
    choices = []
    saved = set(recorded_ids)
    for row in ranking:
        item = row.get("item") or {}
        identifier = str(item.get("id") or "")
        if not identifier or identifier in saved:
            continue
        private = item.get("personal") or {}
        if not private.get("saved") and private.get("feedback") not in ("值得深读", "已用上"):
            continue
        choices.append({
            "id": identifier,
            "title": item.get("title") or "",
            "source": item.get("source") or "未知",
            "url": item.get("url") or "",
            "reason": "你已收藏" if private.get("saved") else "来自你明确标注的阅读反馈",
            "status": "仅建议，尚未加入计划",
        })
    return choices[:limit]
