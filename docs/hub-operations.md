# 私人情报站：使用、部署与恢复

## 本地已经可用

运行 `scripts/hub-docker.sh`，打开 <http://127.0.0.1:8788>。口令在未入库的 `.private/login.txt`，不要贴进聊天或提交 Git。Docker Desktop 需保持运行；页面只绑定本机回环地址。停止用 `docker compose stop`，再次启动用 `docker compose up -d --wait`。不要加 `down -v`，它会删除私人数据库卷。

页面包含精选/候选、来源/时间/主题筛选、收藏、已读、笔记、学习草稿、深入任务进度以及真实同步状态。编辑核验表示核对了卡片所标的材料，**不表示已实际运行推荐工具或读完受限论文**。草稿是待填写的教学提纲，非模型自动生成的完整课程；填写并确认后进入知识笔记，原有课程不会被自动修改。

两个课程继续支持原有 hash 路由、实验、自测、笔记和离线导出。离线 HTML 完全不改。网页副本在原脚本前加载同步桥：同一浏览器首次访问时保留旧 localStorage 并同步；新设备读取云端状态；两份不同则提示选择，并在浏览器保留双方冲突备份。接口使用 revision 防止静默覆盖，多设备冲突要求刷新再选择。

**迁移边界：**浏览器不允许新域名直接读取旧 `file:` 或其他域名的 localStorage。旧页面先导出 Markdown 笔记作保底；同源的 v1/v2/v3 课程迁移沿用原规则。跨域完整进度可使用 `scripts/export-learning-state.js` 在旧页面控制台生成 JSON，再在新门户“循序学习”中导入。所有导入先检查冲突，不覆盖云端已有记录；遇冲突保留原文件，单独选择后再迁移。不要误称已读取用户旧浏览器历史。

## 自动同步

默认本地 Docker 有 `hub` 与 `sync` 两个服务。`sync` 每分钟适配现有编辑记录与候选，内容无变化则批次幂等；每天北京时间 09:00 后首次成功运行现有 `inbox.py collect`。睡眠或 Docker 关闭时不执行，恢复后补采一次。精选仍需在对话中核验并写入编辑记录，后台不会自动冒充核验。

网页显式反馈在下轮采集前写回 `收件箱/feedback.json`；私人笔记不发给采集源。`docker compose logs --tail=30 sync` 查看运行，`docker compose ps` 查看健康状态。失败五分钟后重试，日志有大小上限。`docker compose stop sync` 关闭自动采集/同步，不停止网页。

原 LaunchAgent 路径曾受 macOS 文稿目录隐私权限阻止，已撤下失败任务，默认使用 Docker。不再安装重复的原生定时器；手动使用原收件箱采集菜单前，可先暂停 sync 服务，避免同时改写快照。

手动同步：`.venv/bin/python -m hub.manage sync --url http://127.0.0.1:8788`；加 `--collect` 可先采集。开发用 8787 进程与 Docker 8788 是两个独立数据库，日常统一使用 8788。一键脚本不会将两库隐式互相覆盖。

## 云端包与生产闸口

镜像只含服务代码、固定依赖和两份课程，不含 `AI信息整合`、`.private`、数据库、笔记、日志、账号凭据或完整 Git 历史。`deploy/compose.production.yaml` 包含 Gunicorn、Caddy 和每日备份；数据库、证书和备份均使用持久卷。后台服务以非 root 运行、去除 capabilities、只读根目录，应用端口不映射公网。Caddy 对外仅 80/443，依域名自动申请和续期证书，见 [官方 HTTPS 文档](https://caddyserver.com/docs/automatic-https)。

服务器就绪后，由 Codex 在获准环境执行：

```sh
# 在受控服务器目录，固定到经过检查的提交；TAG 使用实际 SHA。
TAG="<经过验收的提交SHA>"
docker build -t "xunxu-hub:$TAG" .
docker run --rm --user "$(id -u):$(id -g)" -e RELEASE_TAG="$TAG" \
  -v "$PWD:/setup" "xunxu-hub:$TAG" python -m hub.production_init
# 仅在购买、访问授权、DNS及适用备案条件均确认后执行。
CONFIRM_PRODUCTION=yanhaoo.com deploy/start-production.sh
```

配置文件生成后保持 0600，不输出真实 secret。公网访问必须使用 Secure/HttpOnly/SameSite cookie，服务端 CSRF、持久化登录会话撤销、登录限流、同步 token 和请求体上限。CSP 为兼容现有独立课程允许本站 inline 脚本，用户文本统一转义；不是开放用户 HTML 托管。错误登录按连接 IP 限制，反代下可能共同限速；目前单人场景不信任客户端伪造的代理头。

云端不挂载 Mac 目录。在本地同步容器配置 `HUB_SYNC_URL=https://yanhaoo.com` 和与云端一致的独立同步 token（私密 `.env`），由 HTTPS 入站写入云端数据库，自动回取显式反馈。仅在生产确认后修改该配置。私网方案可以保持仅本地监听，通过已授权 VPN/隧道访问；本次没有安装 VPN 或设置公网 DNS。

生产前还需要：实际服务器的 Linux/架构与磁盘核验；SSH 密钥登录；确认备用会话可用后禁用 root/口令登录；防火墙只开放必要端口；操作系统更新；独立异地备份目的地和告警通道。当前没有服务器权限，不把这些写成已完成。实名认证与备案是不同流程，腾讯云 [域名备案准备说明](https://cloud.tencent.com/document/product/243/18905)要求匹配域名所有者与备案主体；实际适用要求以上线地区与官方流程为准。

## 备份、恢复、回滚

在线 SQLite backup 使用一致性 API，不直接复制 WAL 活跃文件。生产 `backup` 容器每日生成一份，验证 integrity_check，保留最近 14 份。健康检查检查备份时间，不包含异地上传；同机备份不能防整机丢失。异地位置、加密密钥和告警渠道需在部署授权时确定。

本地按需备份：

```sh
docker compose exec hub python -m hub.manage backup --target /data/backups/manual.sqlite
# 导出后 chmod 600；该文件必须留在 .private 或受控备份位置。
docker compose cp hub:/data/backups/manual.sqlite .private/manual.sqlite
```

恢复必须先停止写入并保留原库备份：

```sh
docker compose stop hub sync
# 将要恢复的文件放进卷后，使用一次性服务运行恢复命令。
docker compose run --rm --no-deps hub python -m hub.manage restore --target /data/backups/manual.sqlite
docker compose up -d --wait
```

恢复前自动生成 `before-restore.sqlite`；先在隔离库演练，确认 integrity_check、精选数、私人笔记和课程进度，再替换实际库。生产命令添加 `--env-file .env -f deploy/compose.production.yaml`，备份文件位置按实际卷调整，停止 hub 与 backup 后操作。

回滚应用：保留上一版 SHA 镜像，修改私密 `.env` 的 `HUB_IMAGE_TAG`，使用生产启动命令重建服务。当前数据库 schema=1，只建表；未来破坏性 schema 迁移必须先备份并提供兼容恢复。没有现场证据不执行生产回滚。

## 检查和边界

- `.venv/bin/python -m unittest discover -s tests -v`：后端鉴权、日期、去重、状态冲突、备份等。
- `.venv/bin/python scripts/container-check.py`：仅访问本机 8788，验证真实 4 条精选、重启持久化、备份恢复，清理合成验收状态。
- 两套课程分别执行原构建脚本，`git diff --exit-code -- llm-learning.html new-knowledge.html` 应无差异。
- `/healthz` 仅返回存活状态；`/api/status` 需要登录。Docker 自动重启进程崩溃，健康检查本身不会自动修复所有“进程活着但不健康”的故障。
- 本机低负载内存测量只用于容量初判，不能替代云端压测。2 核 4GB 是待购候选；腾讯云产品/报价页此次工具读取失败，未核实地域、续费和流量价格，不能给出已确认报价或代购。

## 2026-10-15 云端私密试运行（取代上面的待购状态）

用户已购买北京轻量服务器：99 元一年、2 核 2GB、50GB SSD、4Mbps、300GB/月，Ubuntu 24.04 x86_64。已经授权并验证专用 SSH 密钥登录；服务器上运行 f299909-amd64 镜像，hub 和每日备份健康。只监听 127.0.0.1:8788，未启动 Caddy、未改 DNS，公网域名与 HTTPS 仍等待备案条件。

本机双击 `打开云端学习站.command`，通过 SSH 隧道打开 <http://127.0.0.1:18788>。云端口令在 `.private/cloud/production-login.txt`，与本地 8788 口令不同。隧道关闭或网络中断后再次双击即可重连。此入口只在本机有效；手机访问需后续域名上线。

云端启动使用 `deploy/start-preflight.sh`，只启动 hub 与 backup。正式域名上线时必须移除 preflight override，恢复 Secure cookie 并启用生产 Caddy；不要将试运行 HTTP 端口绑定到公网。

本地独立 `xunxu-cloud-sync` Docker 项目每分钟复用原收件箱导出，通过已核验主机指纹的 SSH 发送，并回取显式反馈。它不重复采集，不读取网页私人笔记。原本地采集器和本地站点继续工作。启动/检查：

```sh
docker build -f deploy/Dockerfile.sync-ssh -t xunxu-cloud-sync:local .
docker compose --env-file .private/cloud/sync.env -f deploy/compose.cloud-sync.yaml up -d --wait
docker compose --env-file .private/cloud/sync.env -f deploy/compose.cloud-sync.yaml logs --tail=10
```

同步容器只挂载专用私钥及已验证 known_hosts，不挂载 Docker socket 或整个私密目录。停止用同一 Compose 命令的 `stop`。Mac 睡眠、Docker 停止、网络中断期间不会同步；恢复后继续。服务器本身持续服务。云端与本地站点笔记是独立数据库，不自动互相覆盖。

云端每日备份保留最近 14 份，已演练独立恢复。本次另将一致性快照下载到本机 `.private/cloud/cloud-acceptance.sqlite` 并检查完整性；这是一次异地副本，尚未建立自动异地备份和外部告警。服务器 Docker 自动重启已启用。主机口令登录加固、系统更新维护窗口、ICP 提交、正式 DNS/TLS 和公网验收仍需继续完成；不能把私密试运行称为域名正式上线。
