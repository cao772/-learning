# V6 第三阶段｜后端评测与人工标注包（独立研发分支）

本变更不修改 HTML、CSS、JS、课程、生产镜像或现有部署；叠加 [Draft PR #13](https://github.com/cao772/-learning/pull/13) 的 `e84183d` 基线上。

## 已实现

- `hub/v6/sampling.py` 负责可复现的 160 篇/160 对抽样。抽样顺序优先收录所有预算内疑似同事件/疑似转载对，其次高相似但被论文 ID、仓库、版本、时间或类别约束拦截的难例；增加**独立的稀有标题关键词检索**发现可能漏报、分主类别补足文章覆盖，剩余用有随机种子的背景样本完成；标签保留空白。
- 新 `pair-labels.csv` 记录抽样层、候选类型、cosine 和阻断原因，供站主审查及 Codex 前端审核工作台消费，不代表自动判定正负真值。
- `annotation-sample.json` 记录可回放抽样方法、种子、类别覆盖、提议覆盖完整性及层计数。如果候选超过抽样预算，明确 `proposal_coverage_complete=false`，不能声称候选全审。
- P@10 排名前十的事件始终包含在 `relevance-labels.csv` 待标内容中，附原始标题和是否前十标记。
- `evaluate.py` 增加候选 `proposal_false_discovery_rate`（=FP/(TP+FP)），并将旧的误导字段 `false_merge_rate` 保留为 `null`，避免误把候选层的误报写成实际通过人工审核的错归并率。真正的 `approved_merge_error_rate` 依然 `null`，直到有已批准事件簇及人工审核验证证据。Precision、Recall 都**仅对本次人工标注样本**，不能外推全库。

## 下阶段人工评测闸口（尚未通过）

人工复核至少 100 对、至少 100 篇文章、正负例俱全；疑似同事件 2 对必须纳入，最好对困难样本做双人盲标及冲突仲裁。特别注意现有 593 条以论文为主，缺少开源项目、教程、产品与架构的真实多源报道；需先由 Codex 合规补源。样本里找不到足量正例时，继续标记 `blocked`，**不能自动制造人工真值或伪造质量率**。

本阶段不加入任何真实个人数据，不运行新爬虫，不新增计划任务，也不改正式站的每日推荐、公开评分、UI 和数据库；所有算法功能仅从隔离账本离线运行。腾讯云 2C/2GB 仍不承载模型，Mac CPU 继续作为实验端。

## 复核

```bash
python3 -m unittest discover -s tests -v
```

人工标注复核参考 `tests/test_v6_sampling.py` 与 `tests/test_v6_evaluation.py`。CI 浏览器测试不代表本阶段已经做真实人工质量测试。
