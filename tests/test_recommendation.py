import unittest
from hub.recommendation import preference_signals,balance_recommendations


def record(idx, source, category,score=20, feedback=None,saved=False,
           verified='candidate'):
    private={'saved':saved}
    if feedback:private['feedback']=feedback
    return {'item':{'id':str(idx),'title':'Article '+str(idx),
                    'source':source,'personal':private,
                    'verification_status':verified},
            'category':category,'score':score,
            'reasons':['关键词匹配'],'match_keys':[]}


class RecommendationTests(unittest.TestCase):
    def test_only_explicit_feedback_creates_bounded_preferences(self):
        records=[
            record(1,'Site A','paper',feedback='已用上'),
            record(2,'Site A','paper',feedback='值得深读'),
            record(3,'Site A','paper',feedback='证据不好'),
            record(4,'Site B','code'),
            record(5,'Site A','paper',saved=True)]
        signals=preference_signals(records)
        self.assertGreater(signals['category']['paper'],0)
        self.assertEqual(signals['source'].get('site b',0),0)
        self.assertLessEqual(signals['category']['paper'],3)
        adjusted=balance_recommendations(records)
        row=next(x for x in adjusted['ranking'] if x['item']['id']=='1')
        self.assertGreaterEqual(row['score'],row['base_score'])
        self.assertIn('不是内容质量评分',row['reasons'][-1])
        self.assertEqual(row['item']['verification_status'],'candidate')
        self.assertEqual(records[0]['score'],20)

    def test_diversity_balances_top_without_losing_any_item(self):
        records=[record(i,'Site A','agent',score=30-i) for i in range(1,10)]
        records += [record(10,'Site B','paper',score=17),
                    record(11,'Site C','code',score=16)]
        result=balance_recommendations(records,top_window=6,per_source=2,per_category=3)
        prefix=result['ranking'][:6]
        self.assertTrue(any(r['item']['source']=='Site B' for r in prefix))
        self.assertTrue(any(r['item']['source']=='Site C' for r in prefix))
        self.assertEqual({x['item']['id'] for x in result['ranking']},
                         {x['item']['id'] for x in records})
        self.assertEqual(len(result['ranking']),len(records))
        self.assertEqual(result['meta']['model_calls'],0)
        self.assertTrue(result['meta']['not_quality_score'])
        self.assertTrue(any('展示顺序' in ' '.join(r['reasons']) for r in prefix))

    def test_fallback_never_hides_single_source_news(self):
        records=[record(i,'Only Site','paper',score=30-i) for i in range(10)]
        result=balance_recommendations(records,top_window=8,per_source=2,per_category=3)
        self.assertEqual(len(result['ranking']),10)
        self.assertEqual({r['item']['id'] for r in result['ranking']},
                         {str(i) for i in range(10)})

    def test_active_research_is_explicit_not_automatic_promotion(self):
        records=[record(1,'One','code',score=10),record(2,'One','code',score=9)]
        researched={'1':{'decision':'待复现'}}
        signals=preference_signals(records,researched)
        self.assertEqual(signals['explicit_items'],1)
        self.assertFalse(any('已复现' in str(r) for r in balance_recommendations(records,researched)['ranking']))
        self.assertEqual(records[0]['item']['verification_status'],'candidate')

    def test_no_feedback_preserves_existing_order_for_mixed_source(self):
        rows=[record('a','S1','agent',25),record('b','S2','paper',24),
              record('c','S3','code',23)]
        result=balance_recommendations(rows)
        self.assertEqual([r['item']['id'] for r in result['ranking']],['a','b','c'])
        self.assertTrue(all(x['recommendation_adjustment']==0 for x in result['ranking']))


if __name__=='__main__':
    unittest.main()
