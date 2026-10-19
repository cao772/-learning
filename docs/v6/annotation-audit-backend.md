# V6｜离线标注回收与质量审计（非前端模块）

本模块与 [Codex PR #16 人工审核工作台](https://github.com/cao772/-learning/pull/16) 对接，专门验证它导出的 `pair-labels.csv`、`relevance-labels.csv` **是否仍对应原始 `report.json` 和本次后端抽样**。不修改前端、公开页面、生产数据库，不负责用户登录或真人身份认证。

## 执行步骤

1. 在 Codex 离线审核工作台载入同一目录的三份文件，按实际证据人工标注并导出两份 CSV。
2. 将导出的文件保存在 Mac 本地**被 Git 忽略的目录**，不要上传至 public GitHub 仓库；审核代号、原始个人材料、URL 和报告都应按私有研究资产处理。
3. 在离线目录执行（命令需替换成真实路径）：

```sh
python3 -m hub.v6.annotation_audit \
  --report .private/v6-phase2/report.json \
  --pairs .private/v6-phase2/labels-from-ui/pair-labels.csv \
  --relevance .private/v6-phase2/labels-from-ui/relevance-labels.csv \
  --out .private/v6-audit/run1.json
```

如有第二名**实际独立**人工审核者，附带：

```sh
  --second-pairs .private/v6-phase2/reviewer2/pair-labels.csv \
  --second-relevance .private/v6-phase2/reviewer2/relevance-labels.csv
```

命令会阻止覆盖已存在的审计文件；退出码 **0** 仅表示达到*样本可评测*条件，**2** 表示仍需人工标注或仲裁。两份 CSV 上报内容错误、篡改、跨批次或审核者代号相同会直接报错，不能把有缺陷的材料冒充质量评测。

## 检查规则

- 如果原始 `report_id` 是 V6 的 64 位摘要，还会按现有 `offline.py` 算法复算报告内容摘要，防止修改原文后保留旧 report ID。
- 由 `sample_pairs(report.items, report.pairs)` 重新构建唯一的原始抽样集合；校验 **pair_id、left/right URL、可选标题、candidate_kind、sampling_stratum**，拒绝漏行、重复、额外或错配的事件对。
- 根据 `scores` 和抽样文章集合推导推荐标注行；比对事件 ID、关联 URL、Top10 标记与可选标题，防止交换不同事件的数据。
- 非空 `label` 仅允许 `same_event/different_event`；非空 `relevant` 仅允许 `0/1`；必须同时有审核者代号与 `provenance=human` 声明。空标签不得假装已审核。**这些只是导出文件的自我声明，不能据此证明真实身份或杜绝伪标注。**
- 双审核模式对同一项的不同判断生成 `disagreements` 待仲裁清单，审核者代号不得相同；不会自动采用模型意见、覆盖任何原始标签或批准事件归并。
- 建议样本评测就绪闸口：人工标签至少 100 对、覆盖至少 100 篇、真实正负例两种均有、所有 Top10 已标且候选收录预算未溢出；若双审有分歧则继续 blocked。符合这些要求仅是 **`ready_for_sample_metrics`**，不代表 Precision/Recall/P@10 已经达标，也不代表全库召回率。

## 重要边界与当前阻塞

本模块**不会**写 `human` 标签或私自调用 LLM 给它打分，不作自动抽取真实专家判断。Codex PR #16 的浏览器操作同样不能证明真人身份。核实准确率仍需用户/独立人员实际标注与有出处的冲突仲裁；仅获得一致标签也不等于直接发布精选。

目前公开样本集以 arXiv 论文为主，缺工具/教程/产品/架构等足量资料，需由 Codex 使用已接入的公开 GitHub Release 及合规来源补样，并复跑真实精度质量评测。未经过人工质量闸口不得自动生产评分或常驻云端定时任务。

## 自动化测试

```sh
python3 -m unittest discover -s tests -v
```

`tests/test_v6_annotation_audit.py` 使用完全**合成**的 CSV 验证：未填不能验收、双审冲突、不同 ID、跨报告、篡改候选元数据、Top10 或文章映射、错误 `provenance`、report ID 摘要与既有 CSV 输出兼容。这些自动化测试**不是** V6 实际人工精度报告。
