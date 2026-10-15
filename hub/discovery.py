"""Explainable, zero-model personalization for the owner's discovery workbench.

The source directory is a curated list of reading entrances, NOT a statement
that those websites, WeChat accounts, or Xiaohongshu feeds are being scraped.
"""
import datetime as dt
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

INTERESTS = {
    "agent": {"label": "Agent / MCP 技术方向", "terms": (
        "agent", "mcp", "codex", "harness", "skill", "workflow", "智能体", "工具调用", "上下文工程", "推理优化", "llama.cpp")},
    "open_source": {"label": "代码仓库与开源工具偏好", "terms": (
        "github", "开源", "open source", "open-source", "sdk", "repo", "框架", "自托管", "self-host", "产品发布")},
    "algorithms": {"label": "算法、模型与评测", "terms": (
        "benchmark", "eval", "model", "llm", "rl", "transformer", "多模态", "强化学习", "机器学习", "模型", "训练", "推理")},
    "architecture": {"label": "系统架构与工程实践", "terms": (
        "architecture", "database", "docker", "部署", "架构", "可观测", "性能", "数据库", "数据工程", "系统设计", "成本")},
    "product": {"label": "产品经理与商业视角", "terms": (
        "产品", "pmf", "增长", "商业化", "体验", "用户研究", "产品管理", "需求", "路线图", "竞品", "strategy")},
    "research": {"label": "论文与科研偏好", "terms": (
        "arxiv", "paper", "论文", "研究进展", "研究发现", "实验", "理论", "nature", "science", "科研")},
    "science": {"label": "自然、生物与数学探索", "terms": (
        "rna", "biology", "biology", "生物", "基因", "自然", "数学", "物理", "化学", "细胞", "蛋白质", "math")},
    "management": {"label": "技术管理与团队协作", "terms": (
        "项目管理", "技术管理", "管理", "团队", "协作", "流程", "组织", "质量管理", "研发效能", "交付", "roadmap")},
}
DEFAULT_WEIGHTS = {
    "agent": 5, "open_source": 5, "algorithms": 5, "architecture": 4,
    "product": 4, "research": 4, "science": 3, "management": 3,
}
CATALOG = [
    {"name": "AIHOT", "url": "https://aihot.news/all?category=ai-products", "kind": "热点站", "access": "待核验采集接入"},
    {"name": "BestBlogs", "url": "https://www.bestblogs.dev/explore", "kind": "热点站", "access": "待核验采集接入"},
    {"name": "AIGC Weekly · 歸藏", "url": "https://quaily.com/op7418", "kind": "周刊", "access": "来源入口"},
    {"name": "GitHub", "url": "https://github.com/trending", "kind": "开源发现", "access": "可人工保存项目链接"},
    {"name": "小红书", "url": "https://www.xiaohongshu.com/", "kind": "社交平台", "access": "分享或手工添加链接；未接入平台私有数据"},
    {"name": "数字生命卡兹克", "url": "", "kind": "公众号", "access": "Notion 关注清单；未接入抓取"},
    {"name": "机器之心", "url": "", "kind": "公众号", "access": "Notion 关注清单；未接入抓取"},
    {"name": "新智元", "url": "", "kind": "公众号", "access": "Notion 关注清单；未接入抓取"},
    {"name": "量子位", "url": "", "kind": "公众号", "access": "Notion 关注清单；未接入抓取"},
    {"name": "Super黄的念想", "url": "", "kind": "公众号", "access": "Notion 关注清单；未接入抓取"},
    {"name": "云中江树", "url": "", "kind": "公众号", "access": "Notion 关注清单；未接入抓取"},
    {"name": "海外独角兽", "url": "", "kind": "公众号", "access": "Notion 关注清单；未接入抓取"},
    {"name": "通往 AGI 之路", "url": "https://waytoagi.feishu.cn/wiki/QPe5w5g7UisbEkkow8XcDmOpn8e", "kind": "知识社群", "access": "来源入口"},
    {"name": "集智俱乐部", "url": "https://swarma.org", "kind": "学术社群", "access": "来源入口"},
    {"name": "宝玉的分享", "url": "https://baoyu.io/", "kind": "博客", "access": "来源入口"},
    {"name": "Lil'Log", "url": "https://lilianweng.github.io/", "kind": "技术博客", "access": "来源入口"},
    {"name": "Sequoia", "url": "https://www.sequoiacap.com/", "kind": "机构观点", "access": "来源入口"},
    {"name": "a16z", "url": "https://a16z.com/", "kind": "机构观点", "access": "来源入口"},
    {"name": "NYU 语言模型与强化学习课程", "url": "https://izmailovpavel.github.io/ny_fall26_lm_rl_grad.html", "kind": "课程", "access": "来源入口"},
]

PROJECT_CLUES = (
    (("agent", "mcp", "harness", "codex", "skill"), "Muse / CAO 智能体与工具编排"),
    (("多模态", "defect", "视觉", "图像", "vision"), "电力设备缺陷多模态智能体"),
    (("pdf", "docling", "document", "ocr", "图纸"), "P09 图纸重构 / 文档处理"),
    (("知识库", "crawl", "scrap", "采集", "rag"), "通用知识库平台"),
    (("预测", "timeseries", "时序", "forecast"), "P08 时序监视分析"),
)

def normalize_profile(raw):
    raw = raw if isinstance(raw, dict) else {}
    weights = raw.get("weights", {})
    weights = weights if isinstance(weights, dict) else {}
    result = dict(DEFAULT_WEIGHTS)
    for key in result:
        value = weights.get(key)
        if type(value) is int and 0 <= value <= 5:
            result[key] = value
    raw_custom = raw.get("custom_interests", [])
    raw_custom = raw_custom if isinstance(raw_custom, list) else []
    custom = []
    for term in raw_custom:
        if isinstance(term, str):
            term = term.strip()
            if 1 <= len(term) <= 32 and term.casefold() not in [x.casefold() for x in custom]:
                custom.append(term)
            if len(custom) >= 12:
                break
    return {"weights": result, "custom_interests": custom}

def _recent(published_at, today):
    if not isinstance(published_at, str) or not published_at:
        return False
    try:
        days = (today - dt.date.fromisoformat(published_at[:10])).days
        return 0 <= days <= 14
    except ValueError:
        return False

def _project_hint(text):
    for terms, project in PROJECT_CLUES:
        if any(t in text for t in terms):
            return project
    return None

def rank_items(items, profile=None, limit=80, today=None):
    """Rules offer a reading order, never a prediction of quality or Github stars."""
    preference = normalize_profile(profile)
    weights = preference["weights"]
    custom_interests = preference["custom_interests"]
    today = today or dt.datetime.now(dt.timezone.utc).date()
    results = []
    for item in items:
        if item.get("expired"):
            continue
        if item.get("verification_status") == "candidate" and item.get("expires_at"):
            try:
                expiry = dt.datetime.fromisoformat(item["expires_at"].replace("Z", "+00:00"))
                if expiry.tzinfo and expiry <= dt.datetime.now(dt.timezone.utc):
                    continue
            except (ValueError, TypeError):
                continue
        text = " ".join(str(item.get(k) or "") for k in ("title", "summary", "topic", "learning_value", "url")).lower()
        matches = []
        for key, entry in INTERESTS.items():
            if weights[key] and any(term in text for term in entry["terms"]):
                matches.append((weights[key], key, entry["label"]))
        matches.sort(key=lambda x: (-x[0], x[1]))
        custom_matches = [term for term in custom_interests if term.casefold() in text][:2]
        # Capped relevance avoids keyword stuffing dominating unrelated high-quality reading.
        score = 2 + sum(weight * 2 for weight, _, _ in matches[:2])
        explanations = ["匹配：" + m[2] for m in matches[:2]]
        if custom_matches:
            score += 4 * len(custom_matches)
            explanations.extend("新增兴趣：" + term for term in custom_matches)
        if item.get("verification_status") == "reviewed":
            score += 5
            explanations.append("有编辑核验记录（不等于工具已实测）")
        else:
            explanations.append("尚待核验原文")
        if _recent(item.get("published_at"), today):
            score += 2
            explanations.append("最近 14 天发布")
        personal = item.get("personal") or {}
        if personal.get("saved"):
            score += 2
            explanations.append("你已收藏")
        feedback = personal.get("feedback")
        impact = {"已用上": 5, "值得深读": 4, "有趣但暂不用": 0,
                  "现在用不上": -4, "重复": -6, "证据不好": -8}
        if feedback in impact:
            score += impact[feedback]
            if feedback != "有趣但暂不用":
                explanations.append("历史反馈：" + feedback)
        project = _project_hint(text)
        results.append({
            "item": item,
            "score": max(0, score),
            "match_keys": [m[1] for m in matches] + ["custom:" + x for x in custom_matches],
            "reasons": explanations,
            "possible_project": project,  # Keyword hint, NOT a confirmed integration.
        })
    def tie_break(row):
        published = row["item"].get("published_at") or ""
        try:
            ordinal = dt.date.fromisoformat(published[:10]).toordinal()
        except (ValueError, TypeError):
            ordinal = 0
        return (-row["score"], -ordinal, row["item"].get("id") or "")
    results.sort(key=tie_break)
    return results[:limit]

def canonical_link(raw):
    if not isinstance(raw, str) or len(raw) > 2048:
        raise ValueError("链接不能为空或超过 2048 字符")
    url = urlsplit(raw.strip())
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
        raise ValueError("仅接受有效的 http(s) 原文链接")
    if url.port is not None and url.port not in (80, 443):
        raise ValueError("不接受自定义端口")
    host = url.hostname.lower()
    path = url.path.rstrip("/") or "/"
    # GitHub owner/repository identifiers are case-insensitive; deeper paths are not.
    if host in ("github.com", "www.github.com"):
        parts = path.split("/")
        if len(parts) > 2:
            parts[1], parts[2] = parts[1].lower(), parts[2].lower()
            path = "/".join(parts)
    keep = [(key, val) for key, val in parse_qsl(url.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in ("fbclid", "gclid")]
    return urlunsplit((url.scheme.lower(), host, path, urlencode(keep), ""))

def capture_key(url):
    return "capture:" + hashlib.sha256(canonical_link(url).encode()).hexdigest()[:32]
