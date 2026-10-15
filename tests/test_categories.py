import unittest

from hub.content_category import CATEGORIES, classify_item, category_overview
from hub.research import interest_collections


class CategoryTests(unittest.TestCase):
    def test_agent_paper_and_code_are_distinct_primary_categories(self):
        fixtures=[
            ({'title':'Agent MCP 技术实践和 Harness','url':'https://example.com/agent'},'agent'),
            ({'title':'Agent 多智能体论文','url':'https://arxiv.org/abs/2610.10001'},'paper'),
            ({'title':'Agent MCP 源码项目','url':'https://github.com/team/agent-tool'},'code'),
            ({'title':'RNA 的论文分析','url':'https://example.org/analysis'},'paper'),
            ({'title':'GitHub 更新了 Trending 页面','url':'https://github.com/trending'},'other'),
            ({'title':'全栈入门教程','url':'https://example.com/course'},'tutorial'),
            ({'title':'新产品发布','url':'https://example.com/product'},'product'),
            ({'title':'系统架构设计','url':'https://example.com/architecture'},'architecture'),
            ({'title':'蛋白质结构发现','url':'https://example.com/biology'},'science'),
            ({'title':'本周行业融资资讯','url':'https://example.com/news'},'industry'),
        ]
        for item, expected in fixtures:
            with self.subTest(title=item['title']):
                result=classify_item(item)
                self.assertEqual(result['category'],expected)
                self.assertIn(expected,[cat['key'] for cat in CATEGORIES])
        paper=classify_item(fixtures[1][0])
        source=classify_item(fixtures[2][0])
        self.assertIn('Agent',paper['topic_tags'])
        self.assertIn('Agent',source['topic_tags'])
        self.assertIn('许可证',source['category_reason'])

    def test_each_item_counted_once_and_empty_categories_remain_visible(self):
        rows=[
            classify_item({'title':'MCP Agent 做法','url':'https://blog.example.org/a'}),
            classify_item({'title':'Agent paper','url':'https://arxiv.org/abs/2610.12'}),
            classify_item({'title':'Agent source','url':'https://github.com/acme/source'}),
        ]
        counts=category_overview(rows)
        self.assertEqual(sum(x['count'] for x in counts),3)
        self.assertEqual(next(x['count'] for x in counts if x['key']=='agent'),1)
        self.assertEqual(next(x['count'] for x in counts if x['key']=='paper'),1)
        self.assertEqual(next(x['count'] for x in counts if x['key']=='code'),1)
        self.assertEqual(next(x['count'] for x in counts if x['key']=='product'),0)

    def test_cross_source_groups_do_not_mix_primary_categories(self):
        def record(id,url,source,category):
            return {'item':{'id':id,'url':url,'title':'Agent 主题',
                            'source':source},'match_keys':['agent'],
                    'category':category}
        rows=[
            record('agent1','https://example.com/a','Source A','agent'),
            record('agent2','https://example.com/b','Source B','agent'),
            record('paper1','https://arxiv.org/abs/one','Source A','paper'),
            record('paper2','https://arxiv.org/abs/two','Source C','paper'),
            record('code1','https://github.com/a/repo','Source B','code'),
        ]
        groups=interest_collections(rows)
        self.assertEqual(len(groups),2)
        self.assertEqual({g['category'] for g in groups},{'agent','paper'})
        self.assertTrue(all(len(g['members'])==2 for g in groups))
        self.assertTrue(all('·' in g['label'] for g in groups))
        self.assertTrue(all('混编' in g['basis'] for g in groups))


if __name__=='__main__':
    unittest.main()
