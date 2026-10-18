# V6 补源后端：GitHub 官方 Release 适配器（测试阶段）

关联 [PR #13](https://github.com/cao772/-learning/pull/13)、[PR #14](https://github.com/cao772/-learning/pull/14) 和 [Issue #12](https://github.com/cao772/-learning/issues/12)。

本轮仅新增 `hub/v6/github_releases.py` 和后端测试，**未修改公开前端、站主页面、46 课、生产镜像、正式网站、源采集定时任务、域名或生产数据库**。GitHub 仓库 `cao772/-learning` 是 public；本次未上传真实隐私数据/任何 API Token。

## 目的

旧 V6 样本 593 条中论文 453、GitHub 代码/产品/教程类别不足，导致九类别聚簇及公共评分缺少实测素材。本适配器提供一个低权限、低频率的**公开代码发布事件**补源入口。它从固定的 GitHub REST `GET /repos/{owner}/{repo}/releases?per_page=20` 接收用户明确指定的公开仓库，输出普通 V6 `candidate` 观察，不提升核验等级，不作代码运行或许可证审核。

仅处理 GitHub 官方公开 Release **元数据**（标题、tag、发布日期、预发布标记、原文链接）；不复制完整 Release Notes、作者邮箱、下载资产或其他元数据。Released/published_at 才是真实发布时间，缺失保留未知，不能以爬取时间代替。原始仓库所属不同 ≠ 必然独立来源，热度分仍由独立的评分链路保守计算。

## 运行和隔离

```sh
# 在本地已有隔离 V6 state 下执行（这里仅是路径示例，替换成真实目录）
python3 -m hub.v6.github_releases \
  --state .private/v6-verified \
  --repo langchain-ai/langgraph \
  --repo microsoft/autogen \
  --repo huggingface/transformers
```

此命令**只在本机手动执行**，不是新调度器，也不触碰旧采集进程。后端不需要 API Key，也不允许接收自定义 API URL 或任意主机；同一次最多 12 个明确指定的公开仓库，以控制 GitHub 匿名 API 使用量。固定 User-Agent、12 秒超时、最大 1MB 压缩及解压响应、禁止重定向，ETag/If-None-Match 降低重复抓取，429/403 限流时根据 Retry-After 或 X-RateLimit-Reset 保存下次允许时间，不能绕过访问限制。错误不推进成功水位；详情记录在 V6 源运行账本。

`github-release-state.json` 仅存在隔离 state 路径（必须加入本机忽略目录），保存非秘密 ETag 和后退间隔，不保存 Release 正文。首次使用请以**独立目录**运行，确认生产网站当前镜像和 SQLite 没被替换。云主机 2C/2GB 不用于 Embedding 推理。

## 测试与验收边界

```sh
python3 -m unittest discover -s tests -v
```

新 `tests/test_v6_github_releases.py` 使用**合成 HTTP 响应**验证导入、重复/304 幂等、限流持久退避、私有字段不落库、异常 JSON 不推进水位、误指生产数据库拒绝、仓库参数数量及注入防护。

这些自动化测试**不代表真实 GitHub API 已在用户 Mac 通过网络验收**。需要 Codex 在已授权本机环境执行 3–5 个真实公开 repo，记录 HTTP 200 / 304、429 退避、抓取个数、与原 593 条共存并检查复跑 changed=0。新增样本只属于 `candidate`，不直接发布。

## AIHOT 许可与独立补源计划

[AIHOT v1 OpenAPI](https://aihot.news/openapi-v1.json) 支持匿名 GET、ETag 与 `/api/v1/items`；但公开文档明确对外商业产品、代理、公共镜像和批量再分发需另行书面授权。**本轮不把其抓取代码做成默认公网功能，也不复制 AIHOT 的精选/摘要到公开站点**。如果将来用于个人非商业研究，另设权限和保留来源规则；若用于公开再分发，先取得适用授权。

下一步（仍需 Codex 本地真实数据验证）：补 GitHub repo Release、合法产品公告/教程 RSS 与中英平行报道，修订 160 对标注包并人工标注，九类别 coverage 未满足保持 blocked，禁止将测试样本当作人工标注或声称 Precision/Recall/P@10 已达标。
