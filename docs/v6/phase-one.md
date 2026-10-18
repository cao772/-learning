# V6 第一阶段：只读基线与隔离采集账本

关联 Issue #12。研发基于 PR #11 的 3f024e7，不基于旧 main；分支 feature/v6-event-clustering-scoring。此文是阶段验收，不是 V6 完成声明。

## 本次交付

`hub.v6.ledger` 通过显式路径加载已验收的 inbox.py，复用原 RSS/Atom、URL 规范化、缓存/ETag、Retry-After 和限流逻辑。未复制采集器，也未改变生产同步器。

独立 SQLite 保存 source_runs、articles、observations、source_state。每次来源运行都留痕，URL 去重，按来源保存完整公开字段快照。相同来源内容重复执行 changed=0；各来源可不同描述同一个 URL。时间水位仅作观测，不过滤晚到文章；cache_interval/cached 不冒充新抓取，不推进 last_success。来源缺失不删除历史文献。保留 candidate 核验等级，不导入私人兴趣、反馈和笔记。

application_id 守卫拒绝任何非 V6 现有数据库；原采集目录不可用作新 state；进程锁防止同一 state 同时跑批；单来源事务失败完整回滚。撤回方式是停止独立命令、保留或归档其 state；生产 SQLite 无 schema 迁移，无需回滚生产数据。

## 使用

在仓库根目录运行，路径替换为本机真实目录：

```sh
python3 -m hub.v6.ledger \
  --collector /absolute/path/AI信息整合/运行/inbox.py \
  --sources /absolute/path/AI信息整合/运行/sources.json \
  --state /absolute/path/v6-isolated-state
```

离线复跑加 `--offline`。不通过公网 HTTP 暴露账本，没有自动连接原网站。采集失败返回非零并保留成功来源；重跑遵守旧采集器缓存时间与 Retry-After。一般网络错误没有新增指数退避，本阶段不常驻调度。

## 实证（2026-10-18，北京时间）

- 真实公开源：BestBlogs AI RSS 100 条、Quaily Atom 40 条、arXiv cs.AI RSS 453 条，共 593 个规范 URL；均为真实网络返回。Quaily 仍仅作通知，不推测正文。
- 修订后隔离账本用上述真实缓存回放；第二遍各来源 changed=0，593 文献/593 来源观察；数据库 integrity_check=ok。真实抓取与缓存回放明确区分。
- 63 项 Python 测试（含 7 项账本保护/事务/水位/幂等/隐私测试），8 项 Node 测试、原采集器 12 项检查通过；原 30 条回放规则保留；46 课重新构建无差异。
- Docker 隔离容器在 network=none、read_only、cap_drop=ALL 下读取原采集脚本的只读挂载，使用独立 state 完成真实缓存回放；没有挂生产数据卷或发布端口。
- Mac 上 593 条缓存回放一次约 0.12 秒、最大驻留内存 27.6 MB（含 Python 进程，单次样本，非网络/embedding benchmark）。不产生模型 API 费用。
- PR #11 普通 CI 成功；一次 PR 浏览器 smoke 在站主兴趣页超时，另一轮 push smoke 成功。该间歇性失败尚未定位，不标全部 CI 通过。

## 云部署基线（公开脱敏摘要）

只读 SSH 核查：腾讯云北京、Ubuntu 24.04.4 x86_64、2 CPU、约 2GB RAM，50GB 系统盘使用约 13%；网站/备份容器健康，当前镜像标签 32b126f-amd64。运行 app.py SHA256 与该 Git 提交一致；镜像标签不代表容器内存在 Git checkout。

网页仅绑定回环端口，没有 80/443 监听或 Caddy 容器。生产 SQLite quick_check=ok；4 个备份，最新快照 integrity_check=ok。本次没有创建/恢复备份，因此不是新恢复演练。网站最新入库批次与采集/同步心跳不是同一概念。

已有 Mac Docker 每日 09:00 采集、每分钟本地同步，另有通过 SSH 的云端同步器；本轮未新增第二套常驻采集任务。云端没有应用采集 cron；仅网站及备份循环。此前的本机预览隧道本次不可访问，但直接 SSH 到服务内健康检查成功，未重建或关闭隧道。

主机 SSH/防火墙存在上线前加固项，详细结果只保存受控本机文档；云控制台防火墙规则尚未独立核实。域名 A 查询未返回地址。官方备案网站本次无法读取，无审核通过证据，备案仍由用户处理，绝不据此宣称通过。

资源建议：该规格可留作网站、SQLite、小批采集/队列；多语 embedding 先在 Mac 测量 CPU/内存，再决定迁移，未在云上安装或运行模型。

## 后续阶段与明确未完成项

1. AIHOT v1 与 GitHub REST 适配、分页/撤稿/条件请求和持久退避；本次只核对 AIHOT 官方接口说明，未冒充已实现 API 接入。
2. MinHash + 多语 embedding（时间/实体约束），人工归并队列；公共多维评分与私人排序严格分离。当前没有语义聚簇或质量分数。
3. 100–200 条人工标注与聚簇 precision/recall、错误合并率、P@10 评测。当前 593 条是真实采集材料，不是人工标注集，质量指标不可用。
4. 新调度接管前确认单一采集拥有者，防止双重抓取；日报、后台设置、评分解释和迁移/恢复演练待后续。
5. 修复既有间歇性浏览器 CI；云端灰度前准备备份、恢复和备用 SSH。未经生产授权不修改 SSH、防火墙、DNS、端口或运行服务。

接口依据：[AIHOT 官方 Agent/API](https://aihot.news/agent?tab=api)。模型与评分调研列在 Issue #12，本阶段不把方案当成实现。
