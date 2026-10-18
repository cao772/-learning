# V6 第二阶段：离线候选归组与可解释评分

日期：2026-10-18。沿用 Draft PR #13，基线 d8973fa8。**工程回归通过不等于质量验收通过**；当前人工真值为零，不启用生产评分或自动调度。

## P0 修正

- schema 2 区分 last_observed_at（包括缓存）、last_fetched_at（真实成功返回）、last_changed_at（公开正文改变）、last_validated_at（成功返回或304）。缓存不改正文和新鲜度；旧 last_seen 不再推进，不参与评分。旧库时间语义不可靠，新列保留 NULL，不虚构历史。
- observations 保存每个来源的公开正文。articles 按来源 ID 稳定选择代表正文，完整来源正文集合进入内容版本指纹。同 URL 来源写入顺序不影响代表内容、候选与评分；代表源排序不是可信度排序。
- 嵌套 sources/categories 强类型、长度和字段白名单；删除任意 metadata/笔记字段，拒绝内网、凭据及敏感查询参数 URL。不能保证任意自由文本没有隐私：输入仅限授权公共采集器，禁止接入私人笔记。
- 迁移前使用 SQLite backup 生成 `.private/v6-before-phase2.sqlite`。原 593 条账本原位迁移，未重建。迁移在事务中；回滚需停止隔离研究进程，使用该备份和第一阶段代码，不能让旧代码直接写 schema 2。生产库始终拒绝打开。

## 算法与人工审核

64 维稳定 MinHash，词/中文字符三元 shingles，再以精确 Jaccard 核验近似重复。当前 593 条使用全对比较，O(n²)，不是已验证的大规模索引。CPU 多语言向量采用 [MiniLM-L12-v2](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)，revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`，384 维，2线程、batch16。推理仅本地 safetensors，不执行远端代码、不调用付费 API。

候选筛选 cosine≥0.62 或 Jaccard≥0.78。疑似转载要求至少15个 shingles、Jaccard≥0.78；疑似同事件要求 cosine≥0.82、共享名称线索、72小时发表时间窗及同主类别。缺时间、版本号冲突、不同 arXiv 论文ID、不同 GitHub 仓库ID均阻止事件归并。名称线索是保守规则，不是完整实体识别。高相似但不同事件保留 same_topic。

所有语义归并均须明确人工确认。审批绑定双方完整公开正文指纹，材料改变即失效；complete-link 防止 A-B、B-C 的批准偷偷合并未审批 A-C。审核文件仅本地，没有公开写入接口。

```sh
python3 -m venv .private/v6-env
.private/v6-env/bin/pip install -r requirements-v6.txt
# 模型首次下载需网络，只下载公开模型文件；后续推理离线。
.private/v6-env/bin/python -c "from huggingface_hub import snapshot_download; snapshot_download('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', revision='e8f8c211226b894fcb81acc59f3b34ba3efd5f42', local_dir='.private/v6-model', allow_patterns=['*.json','*.txt','*.model','model.safetensors','1_Pooling/*'])"
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .private/v6-env/bin/python -m hub.v6.offline \
  --db .private/v6-verified/v6.sqlite --model .private/v6-model \
  --revision e8f8c211226b894fcb81acc59f3b34ba3efd5f42 \
  --out .private/v6-phase2 --as-of 2026-10-18T08:00:00+08:00
python3 -m hub.v6.review --report .private/v6-phase2/report.json \
  --store .private/v6-phase2/reviews.json --pair PAIR_ID --decision merge --reviewer REVIEWER
# 重跑分析时加 --reviews 路径；有标注后若报告改变必须换 --out，保护旧标注。
python3 -m hub.v6.evaluate --report .private/v6-phase2/report.json \
  --pairs .private/v6-phase2/pair-labels.csv --relevance .private/v6-phase2/relevance-labels.csv
```

## 公共分数和私人排序

公共评分纯函数不接受私人偏好。五轴为重要性、信息增量、证据、可用性、扩散，九类分别加权（代码 `scoring.WEIGHTS`）。当前前两轴未知，返回 null、贡献0；摘要存在、来源类型仅是低权重元数据线索，不伪造全文核验/代码运行/论文复现。输出权重、缺失证据、原始URL、规则版本和解释，核验等级始终 candidate。

热度 = 100 × (1-exp(-独立来源下界/3)) × 2^(-发表后天数/2)。只用原文发表时间，缺失或未来日期不补采集时间。聚合站来源独立性未知算0，近似转载跨域也不重复计数；注册域粗粒度合并可能低估，不能据此声称来源确实独立。当前是未校准注意力分，不是最终优质推荐。站主类别偏好投影在独立 `private_ranking.py`，公共 runner 不导入它，私人输入不进入报告。

## 真实案例与性能

沿用 BestBlogs100、Quaily40、arXiv453，共593条。最终2465个关系候选，2对疑似事件待人工确认，0次自动语义归并。

- STEPX Neo：BestBlogs [72f6cf93fa](https://www.bestblogs.dev/article/72f6cf93fa) 与 [aa73f6108d](https://www.bestblogs.dev/article/aa73f6108d)，cosine≈0.925，时间差约1.26小时。可能同发布事件，但聚合站两条链接不算两个独立新闻源。
- Meta Muse Wonder：[66c48b3cd6](https://www.bestblogs.dev/article/66c48b3cd6) 与 [fb830c83ef](https://www.bestblogs.dev/article/fb830c83ef)，cosine≈0.870，约8.07小时。仍须核原文。
- 错误归并风险：[2406.20031](https://arxiv.org/abs/2406.20031) 与 [2610.21554](https://arxiv.org/abs/2610.21554) 相似度≈0.902，但不同论文，新增 ID 约束后阻止。共拦截首轮5个此类论文候选。此为开发观察，不是人工质量基准。
- 相邻周刊182/183相似度≈0.998，超72小时窗，不能同事件。
- 合成中英版本场景：同一 Widget2.0 中英描述≈0.941可提候选，2.0与3.0即使≈0.928也因版本冲突阻止；合成场景不计真实标注集。

Mac 首轮无向量缓存：8.563秒向量、9.650秒总耗时，峰值894,877,696字节。最终缓存运行数据见 `phase-two-evidence.json`。测量为单次进程峰值，不能外推到2GB云主机或百万条规模。向量相似度改用显式 reduction 并拒绝非有限值，避免本机 BLAS 状态警告。环境 Python3.9/LibreSSL 的 urllib3 警告仅发生导入；本轮推理完全离线。

独立回放测试每来源缓存5遍：593条、changed=0、公开表示和分数均不变。完整原始报告、数据库、模型、向量、标注包在忽略目录 `.private/`，不提交公共仓库。

## 验收和未完成项

本轮83项Python、8项Node检查；46课重构建无差异。GitHub CI 包含 Docker build 和真实 Chromium 合成数据烟测，精确提交及链接写入 PR 最新评论。

160篇分层文章和160对标注表已生成，含前10排序；label/annotator/provenance 留空。人填写 same_event/different_event、评审者及 provenance=human；相关性填0/1。评测要求至少100对、覆盖100篇、正负例都有，且report_id匹配；缺失返回null和退出码2。P@10须前10项均有人标。样本指标只代表所标样本，不能外推全库召回率。

真实样本主类别：论文453、待分类69、Agent61、跨学科8、行业2；缺代码/产品/教程/架构类别，尚不能宣称九类质量验收通过。当前人工标注为0，precision/recall/误合并率/P@10全部待验证。评分重要性/增量、来源独立性与权重也待人工校准。

保持现有前端与课程、云端生产数据库、本地稳定服务、调度和公网端口不变；研究依赖不进入生产镜像。不合并 main、不自动部署。下一步是人工样本评测与类别补样，之后才决定生产评分/调度上线。
