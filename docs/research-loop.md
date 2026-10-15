# 循序 learning｜跨来源对照与研究验证闭环（V2）

状态：2026-10-15，独立 Draft 开发分支，**没有部署到腾讯云**。目前云端 SSH 隧道预览仍运行已验收的公开阅读版；`yanhaoo.com` ICP 审核尚待核实。保留原有 30+16 节课程，不修改热点收件箱的真实采集逻辑。

## 功能与页面

在站主登录后的「兴趣发现」中新增两页：

1. **跨来源线索**：对现有排名前 80 条记录、至多 100 条私人分享链接进行规范 URL 完全匹配；同一篇文章在多个入口出现时展示各自来源与核验状态。对不同 URL 的**完全一致、较长标题**列出疑似相关项供人工核实。不会把重复收录算作独立证据，不做语义相似度冒充，也不会将候选升级编辑精选。
2. **验证与学习计划**：每条热点或手工链接可进入私人研究记录，记录要验证的问题、对应项目、预计工作量、复现状态、证据、反例和下一步阶段。通过现有 `/api/state/<key>` 加入 `research:` 私人命名空间，SQLite 持久化、revision 冲突检测、备份/导出复用；访客无权访问。
3. **按来源类型提供人工核查清单**：GitHub 仓库提醒核对许可证、维护、可安装性与改造成本；论文提醒原文/实验/数据/可复现性；教程与产品提醒事实/观点/证据/小试。**GitHub stars、许可证、最近维护日期、论文已阅读全文、真实复现实验等指标仍为未知**，不会触发外部 API、不会伪造质量评估。
4. **以现有 4 条编辑精选 + 候选 + 私人收藏为基础**；不保证每个主题均有跨源匹配。只有确实匹配时才展示关联。

## 安全边界

- `GET /api/discover` 必须登录；新响应中的 `connections`、`research_guides` 与 `research_records` 仅供站主，匿名 `/api/items` 及首页不会包含私人研究记录。
- 记录通过现有 `PUT /api/state/research:<id>` 写入，要求登录与 CSRF；采用数据库 revision 乐观锁，不静默覆盖另一设备数据。
- 对公开来源标题、内容、用户笔记进行 HTML 转义；外链仅接受 http(s)，新功能不访问这些链接，因此不引入服务端 SSRF。
- GitHub 质量清单仅提供提问，不意味着已连接 GitHub API 或执行代码；小红书/微信公众号保留手工输入边界。
- 根据用户新兴趣扩展研究计划，不因固定职业标签而阻断科学探索；评估决策需要人工填写。

## 验收

```sh
python -m unittest discover -s tests -v
node --check hub/static/discovery-ui.js
node --check hub/static/research-ui.js
node --test tests/research-ui.cjs
node scripts/build-course.cjs && node scripts/build-new-knowledge.cjs
git diff --exit-code -- llm-learning.html new-knowledge.html
```

需要验证：链接完全一致可关联；同标题不同链接只提示不自动合并；不同短标题不得归并；匿名不可读私人记录；CSRF、revision 冲突、SQLite 持久化；站主页面 HTML 转义；原课程构建无变化。

**未完成**：真实云端新版部署、微信/小红书自动订阅、GitHub 星数及 Issue 真实查询、论文全文核验与任何自动实验、线上浏览器端到端验收。不能将 CI 成功写为这些功能已完成。
