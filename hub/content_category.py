"""Non-generative display categories for imported reading materials.

One PRIMARY presentation category per item. Agent is a topical category,
while papers and code repositories are formats; topic tags remain independent.
This avoids displaying one article in several top-level columns.
No network requests and no claims that a repository has a valid open license.
"""
import re
from urllib.parse import urlsplit

CATEGORIES = (
    {"key":"agent","label":"Agent 与智能体","description":"Agent、MCP、Harness、工具调用等技术实践"},
    {"key":"paper","label":"论文与科研","description":"论文原文、科研进展与研究成果"},
    {"key":"code","label":"开源工具与代码项目","description":"代码仓库、SDK 与开源工具；许可证需核验"},
    {"key":"product","label":"产品与应用","description":"可用软件、产品发布及体验"},
    {"key":"tutorial","label":"教程与实践","description":"技术教程、案例、操作指南"},
    {"key":"architecture","label":"架构与工程","description":"系统设计、工程化、性能与部署"},
    {"key":"science","label":"跨学科探索","description":"自然、生物、数学和其他领域"},
    {"key":"industry","label":"行业动态与观点","description":"AI 行业新闻、分析与商业观点"},
    {"key":"other","label":"待分类","description":"证据不足，不依据猜测强行归类"},
)
LABELS = {row["key"]:row["label"] for row in CATEGORIES}

PAPER_HOSTS = frozenset({"arxiv.org","www.arxiv.org","doi.org","www.doi.org",
                         "openreview.net","www.openreview.net","nature.com",
                         "www.nature.com","science.org","www.science.org"})
REPO_HOSTS = frozenset({"github.com","www.github.com"})
RESERVED = frozenset({"trending","topics","marketplace","settings","features",
                      "explore","login","pricing","collections","orgs","apps","about"})

def phrase(pattern, value):
    return bool(re.search(pattern, value, re.IGNORECASE))

def _url_kind(url):
    try:
        u=urlsplit(url or "")
        host=(u.hostname or "").casefold()
        parts=[p for p in u.path.split("/") if p]
    except (ValueError,TypeError,AttributeError):
        return None
    if host in PAPER_HOSTS:
        return "paper"
    if host in REPO_HOSTS and len(parts)>=2 and parts[0].casefold() not in RESERVED:
        return "code"
    return None

def classify_item(item):
    """Return a display label with a reason and independent topic tags.

    The URL gives higher-confidence *format* clues than a title keyword.
    A blog post merely mentioning GitHub is NOT classified as a code project.
    A paper on Agent may carry the Agent tag while remaining under Papers.
    """
    title=str(item.get("title") or "")
    summary=str(item.get("summary") or "")
    subject=str(item.get("topic") or "")
    text=" ".join((title,summary,subject))
    url_kind=_url_kind(item.get("url"))
    tags=[]
    if phrase(r"\b(?:agents?|agentic|mcp|harness|codex|tool.calling)\b|智能体|多智能体|工具调用|上下文工程",text):
        tags.append("Agent")
    if phrase(r"\b(?:llm|model|benchmark|eval|transformer|rlhf)\b|大模型|算法|评测|机器学习|强化学习",text):
        tags.append("算法与模型")
    if phrase(r"\b(?:rna|biology|genome|protein|math|physics|chemistry)\b|生物|数学|自然科学|基因|蛋白质|物理",text):
        tags.append("跨学科")
    if phrase(r"架构|工程化|系统设计|部署|数据库|可观测|性能优化",text):
        tags.append("工程架构")

    if url_kind:
        key=url_kind
        reason=("根据原始论文平台链接归类（全文及结果待核验）" if key=="paper"
                else "根据 GitHub 仓库链接归类（许可证与质量待核验）")
    elif phrase(r"\b(?:paper|preprint|arxiv)\b|论文|预印本|科研成果|研究报告",title):
        key="paper"
        reason="根据标题暂归论文研究，是否原始论文待核验"
    elif phrase(r"\b(?:open.source|opensource|github repository|sdk)\b|开源项目|开源工具|开源框架|代码仓库",title):
        key="code"
        reason="标题提示代码/开源项目，实际许可证与可运行性待核验"
    elif "Agent" in tags:
        key="agent";reason="内容关键词显示 Agent 技术主题，暂时归类"
    elif phrase(r"\b(?:tutorial|cookbook|walkthrough|how.to|guide)\b|教程|手把手|实战指南|入门指南|上手教程",title):
        key="tutorial";reason="标题呈现教程或操作指南特征，待人工核实"
    elif phrase(r"\b(?:product|app|saas|launch)\b|产品发布|新产品|产品测评|应用工具|软件工具",title):
        key="product";reason="标题呈现产品/应用信息，待人工核实"
    elif phrase(r"\b(?:architecture|devops|database|infrastructure)\b|系统架构|部署实践|工程实践|性能优化",title):
        key="architecture";reason="标题包含工程架构主题，暂时归类"
    elif "跨学科" in tags:
        key="science";reason="内容出现跨学科关键词，暂时归类"
    elif phrase(r"行业|产业|市场|融资|新闻|资讯|趋势|观点|政策|商业分析",title):
        key="industry";reason="标题呈现行业资讯或观点特征，暂时归类"
    else:
        key="other";reason="信息不足，保留待分类，未作虚假判断"
    return {"category":key,"category_label":LABELS[key],
            "category_reason":reason,"topic_tags":tags[:4]}

def category_overview(ranking):
    counts={row["key"]:0 for row in CATEGORIES}
    for record in ranking:
        key=record.get("category","other")
        counts[key if key in counts else "other"]+=1
    return [{**entry,"count":counts[entry["key"]]} for entry in CATEGORIES]
