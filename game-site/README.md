# 游戏直接入口

主页新增“游戏”链接，访客打开 `/game/` 后直接进入 Godot 游戏画布。没有介绍页、iframe、外部操作说明或额外启动按钮；旅程选择由游戏自身提供。

## 装配

先准备名为 `game` 的 Godot Web 导出：

```sh
python3 game-site/tools/build.py --runtime /path/to/public-web-export
python3 -m http.server 8320 --directory game-site/dist
```

访问 `http://127.0.0.1:8320/`，不能使用 `file://`。装配器从白名单复制运行文件、加入完整第三方许可，并把 `game.html` 复制为 `index.html`，直接自动加载。游戏 HTML 和首页入口使用相同资源基名与存档来源。

装配器校验 Godot `fileSizes`，生成各文件 SHA256 和确定性 gzip。压缩前后解压字节一致，不改变画面质量。运行输出与清单已加入 Git 忽略，不提交巨大 PCK/WASM。

只取 Godot 的固定运行文件，不复制工程目录、原稿、聊天、Notion、作者资料、凭据或生产快照。PCK 内公开内容必须在游戏导出阶段审核；文件白名单不能代替 PCK 内容审核。

## 网站部署

Caddy 为 `/game/` 提供静态路由；Compose 将站点根目录的 `game-public/` 只读挂载为 `/srv/game`。先把已验收的 `dist/` 内容复制到 `game-public/`，不复制本地 `.game-build-output` 标记；校验 Caddy 配置后按现有流程发布挂载与主页模板。

后续更新使用独立版本目录，按清单校验后切换，保留旧版本回滚。HTML、JS、PCK、WASM 与 worklet 必须一起替换。Caddy 使用 `no-cache` 防止混用旧文件，并提供预压缩 gzip。WASM 的 MIME 应为 `application/wasm`。

本分支基于 `codex/local-latest`；远端 `main` 尚无该 Flask/Caddy 网站。线上首页与路由比此基线更新，生产部署必须对当时运行的镜像与配置做最小补丁，复用现有静态挂载，不能用本分支旧模板整份覆盖生产。生产快照、部署身份和私密发布脚本不在仓库中。PR 保持草稿，不自动合并。

发布验证包括直接进入画布、各旅程与存档、鼠标控制、WASM MIME/gzip、原有网站与私密接口边界。完整第三方许可见 `public/licenses/`，与游戏一起部署。
