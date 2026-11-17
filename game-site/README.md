# 游戏直接入口

主页只有一个“游戏”链接，目标是独立子域名 `https://game.yanhaoo.com/`，直接进入 Godot 游戏画布。没有介绍页、iframe、外部操作说明或额外启动按钮；旅程选择由游戏自身提供。

## 装配

当前接入版本为 033。游戏工程与运行文件由游戏项目维护；网站只负责一个“游戏”导航和静态入口，不另外制作介绍页面。

对已经完成网页壳与预压缩的 033 导出，使用：

```sh
python3 game-site/tools/build.py --runtime /path/to/visual-quality-033-20261117/site --prepared --release 033
```

装配器从白名单复制运行文件、加入完整第三方许可，并把 `game.html` 复制为 `index.html`，直接自动加载。游戏 HTML 和首页入口使用相同资源基名与存档来源。`--prepared` 保留已完成的加载画面和键盘处理，并复用未改动运行文件的同批 `.br`、`.gz` 副本。传入目录应是已经整体产出的发布目录，不能混入其他版本的压缩副本。

装配会为公开内容生成带内容摘要的版本号，例如 `game-033-<内容摘要>`，记录在本地 `build-manifest.json` 的 `release_id` 字段。`game.html` 和 `index.html` 都加入 `<base href="/game-assets/<release-id>/">`，使这个页面后续的 JS、PCK、WASM、worklet 和图片请求固定到子域名内的同一版。浏览器地址是 `https://game.yanhaoo.com/`。旧 `<base>` 会先移除；HTML 改写后不复用旧压缩副本，而是重新生成 gzip，构建机有 Node.js 时同时生成 Brotli。

装配器保留原有文件尺寸与内容边界保护，生成本地文件清单；缺少 gzip 的文本或运行文件会生成确定性 gzip。Brotli 与 gzip 都不改变解压后的内容。运行输出与清单已加入 Git 忽略，不提交巨大 PCK/WASM。对未经网页壳处理的标准导出，可省略 `--prepared`，继续使用原通用装配方式。

只取 Godot 的固定运行文件，不复制工程目录、原稿、聊天、Notion、作者资料、凭据或生产快照。PCK 内公开内容必须在游戏导出阶段审核；文件白名单不能代替 PCK 内容审核。

## 网站部署

Caddy 的 `game.yanhaoo.com` 独立站点通过已有 `lab-public` 只读挂载提供两个路由：

- 子域名根路径 `/` 指向 `/srv/lab/game`，这是当前版本的相对符号链接；入口文档采用 `no-cache`。
- `/game-assets/<release-id>/` 指向 `/srv/lab/.game-releases/<release-id>/`，采用一年 `public, max-age=31536000, immutable` 缓存。

把本次 `dist/` 的公开内容放进 `lab-public/.game-releases/<release-id>/`，不复制本地 `.game-build-output` 标记，再切换 `lab-public/game` 相对链接到 `.game-releases/<release-id>`。同一子域名后续发布时，已打开的旧页面仍使用自己的版本资源，不会因入口切换而混用新旧 JS、PCK 或 WASM。主页入口为唯一的 `<a href="https://game.yanhaoo.com/">游戏</a>`，后续升级不重复添加导航。

主站 `yanhaoo.com` 不提供游戏静态文件；旧 `/game`、`/game/*` 只重定向到子域名。游戏站点没有 `reverse_proxy hub`，游戏请求不进入 Flask 应用。当前方案仍共享 Caddy、服务器与网络带宽，并不是独立物理服务器或独立带宽。

每个版本目录发布后保持不变，不可在同一版本路径覆盖新内容。HTML、JS、PCK、WASM、worklet 与其压缩副本作为一组保存；回滚只恢复入口链接和必要配置，保留旧版本供已打开页面继续读取。Caddy 按客户端能力优先提供预压缩 Brotli，其次 gzip，再回退原文件。游戏仅由浏览器执行，网站服务器提供静态文件。

浏览器存档按 origin 隔离。由旧主域名迁到子域名，不会自动搬迁 `yanhaoo.com` 的 IndexedDB；旧站数据不会被这次源码修改删除，后续如需跨站迁移应单独实现导出/导入。

本分支基于 `codex/local-latest`；远端 `main` 尚无该 Flask/Caddy 网站。线上首页与路由比此基线更新，生产部署必须对当时运行的镜像与配置做最小补丁，复用现有静态挂载，不能用本分支旧模板整份覆盖生产。生产快照、部署身份和私密发布脚本不在仓库中。PR 保持草稿，不自动合并。

生产发布由当前整合任务的主执行者完成，保留并发写入前置条件、旧配置和回滚版本。此仓库装配命令不连接服务器、不启动浏览器、不运行游戏、测试或部署 QA；用户明确提出检查或试玩时再另行执行。不要复用此前 032 带自动 probe/健康检查的私密发布脚本。

完整第三方许可见 `public/licenses/`，与游戏一起部署。033 的实际画面与行为由游戏工程交付；本次网站接入更新未运行检查、测试或试玩。

## 本轮发布记录

旧路径 `https://yanhaoo.com/game/` 曾完成 `game-033-80f791f58c51` 的部署命令；之后作者要求改用独立游戏子域名。当前记录为**迁移中**：目标 `https://game.yanhaoo.com/` 的 DNS、HTTPS 和生产路由切换由主执行者处理，这次源码归档不代表新域名已上线。按作者要求未运行 HTTP、浏览器、游戏或其他 QA，不宣称体验验收通过。
