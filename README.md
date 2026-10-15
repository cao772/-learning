# 循序 learning

把大模型知识和新技术资料整理成可以离线阅读、动手实验和记录理解的中文学习网页。

## 开始学习

下载仓库后，用浏览器打开对应 HTML。阅读与本地实验无需安装依赖、账号或 API Key；外部参考资料链接需要联网。GitHub 文件页展示源码，下载 HTML 后才能直接学习。

- [大模型、强化学习与推理 · 30 课](llm-learning.html)：从分词、概率与 Transformer，学习到后训练、强化学习、工具、RAG 和评测。[使用说明](使用说明.md) · [课程目录](课程目录.md) · [课程主线](课程主线.md)
- [新知实验室 · 16 课](new-knowledge.html)：从 BestBlogs 和 AIHOT 的知识线索进入上下文工程、Agent、评测与推理效率。[使用说明](新知实验室-说明.md) · [课程目录](新知实验室-目录.md)

每课围绕具体问题推进，包含循序讲解、例子、实验和自测。讲解段数随主题变化，关键推理直接显示；没有装饰性的“本课的信息路径”流程条。进度与笔记保存于当前浏览器，可导出 Markdown。

课程是标明整理日期的学习快照。中文教学场景与数字实验用于解释机制，不代表真实模型性能实测。

## 复用 Skill

[循序学习 HTML Skill](skills/xunxu-learning-html/SKILL.md) 包含设计与教学规则、[编写指南](skills/xunxu-learning-html/references/authoring.md)和[完整参考页面](skills/xunxu-learning-html/assets/reference.html)。将 `skills/xunxu-learning-html` 整个目录复制到个人 Codex skills 目录后使用。

示例请求：用 xunxu-learning-html，把这些资料整理成能学懂的中文交互学习网页。

## 修改和构建

阅读成品不需要 Node.js；修改源码后使用 Node.js 执行，无第三方 npm 依赖：

```sh
node scripts/build-course.cjs
node scripts/build-new-knowledge.cjs
```

- `src/`：基础课程数据、模板、讲解与交互代码。
- `src/new-knowledge/`：新知课程、循序讲解、来源与离线实验。
- `scripts/`：生成 HTML 与目录的构建脚本。
- `skills/`：可复用的学习页面 Skill。

修改新知页面后，如需同步 Skill 的参考实例，将生成的 `new-knowledge.html` 复制到 `skills/xunxu-learning-html/assets/reference.html`。

## 验证

构建脚本检查课程内容结构与来源等约束。交付前已进行 Chromium 桌面与窄屏页面、导航、实验、自测、笔记和导出检查；后续修订按受影响范围补验。浏览器自动化使用本地 HTTP，未据此保证所有浏览器在 `file:` 下的存储行为。具体历史检查范围见两套课程的使用说明。
