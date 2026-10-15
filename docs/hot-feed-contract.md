# 现有收件箱接入契约 v1

本实现复用既有采集器；`hub/manage.py export_source()` 只适配输出，不请求任何上游资讯网站。上游在本地 `AI信息整合`，公开仓库不包含该目录。没有此目录的环境可以启动空站，或通过鉴权入站接受数据，不能宣称采集已接通。

输入：`收件箱/snapshot.json`、`review-packet.json`、`status.json`，以及 `成果/*-编辑记录.json`。最多 30 个候选，编辑记录作为精选事实源；摘要、核验范围、限制和推荐理由逐字段传递。原始发布时间未知则为空；采集时间单列。深入任务文字显示为待执行材料，实际进度属于个人记录。

输出：`{schema:1, items:[...], source_status:{...}}`，每条包含：

| 字段 | 含义 |
|---|---|
| id / url | 上游规范 URL 的稳定 ID、原始入口；版本链接保留版本 |
| title / source / sources / topic | 标题、发现渠道及追溯元数据、主题 |
| published_at / collected_at | 原始日期与快照采集时间，不能互换 |
| verification_status | candidate / reviewed；精选须包含证据、范围和个人价值 |
| summary / scope / verification_notes | 上游摘要或编辑摘要、读取范围、限制 |
| learning_value / next / evidence | 编辑推荐理由、下一步、支持结论的原始链接 |
| expires_at | 候选继承上游快照到期时间；读取时清除到期候选正文，个人收藏/笔记不删除 |
| task | 已准备的深入任务，不能表示实验已经完成 |

导入接口 `POST /api/ingest` 要求独立 Bearer token，JSON 上限 2MB、最多 1000 项；来源协议要求 http(s)。批次以规范化 payload 的 SHA256 去重，条目以上游 ID upsert。上游负责规范 URL 和精确去重；不同 ID 的语义/DOI 别名不由后端猜测合并。相同版本二次同步不重复；candidate 不能覆盖 reviewed。没有编辑记录的摘要不能自动升级精选。

`GET /api/sync-feedback` 使用同步 token，只返回显式标签、时间和条目 ID，不返回私人笔记。同步程序将它们幂等写回收件箱反馈，在下一次采集前生效。支持六种上游标签；未读和浏览不构成反馈。远端通信仅允许 HTTPS，本机回环测试允许 HTTP。token 不进入浏览器。

本地 Docker `sync` 每分钟检查并导出，09:00 后每天首次成功执行现有采集器；错过时间时在下次容器运行补采一次，不回填全部历史。不依赖模型。采集失败可继续显示其他来源；同步失败保留原有入库数据、记录失败并五分钟后重试。浏览器“任务状态”显示最近成功批次与上游来源状态，无法代表网络失联时的远端实时状态。

私人数据位于 SQLite volume；本地源文件通过 Docker 挂载进入同步容器，不打包进镜像、不提交仓库。云端不挂载 Mac 路径，改用 HTTPS token 上传；正式云端接入前不会改动 DNS。
