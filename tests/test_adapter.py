import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from hub.manage import export_source,import_feedback

class AdapterTests(unittest.TestCase):
 def test_editorial_survives_feed_window_and_feedback_idempotent(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'收件箱').mkdir();(root/'成果').mkdir()
   row={'id':'candidate','title':'synthetic','url':'https://example.org/a','scope':'标题','sources':[{'name':'fixture'}]}
   (root/'收件箱/snapshot.json').write_text(json.dumps({'items':[row],'generated_at':'2026-10-15T00:00:00+00:00','expires_at':'2026-10-17T00:00:00+00:00'}))
   (root/'收件箱/review-packet.json').write_text(json.dumps([row]))
   card={'id':'archived','title':'synthetic editorial','published_at':'2024-07-18','type':'explore','what':'fixture','scope':'摘要','limits':'未读全文','why':'探索','next':'读方法','evidence':[{'label':'original','url':'https://example.org/original','supports':'fixture'}]}
   (root/'成果/test-编辑记录.json').write_text(json.dumps({'date':'2026-10-14','cards':[card],'deep_task':'待执行'}))
   result=export_source(root);self.assertEqual(len(result['items']),2)
   reviewed=next(x for x in result['items'] if x['id']=='archived')
   self.assertEqual(reviewed['published_at'],'2024-07-18');self.assertIsNone(reviewed['collected_at']);self.assertEqual(reviewed['scope'],'摘要')
   events=[{'id':'candidate','label':'现在用不上','at':'2026-10-15T00:00:00+00:00','note':'网页显式反馈'}]
   import_feedback(root,events);import_feedback(root,events)
   self.assertEqual(len(json.loads((root/'收件箱/feedback.json').read_text())),1)
if __name__=='__main__':unittest.main()
