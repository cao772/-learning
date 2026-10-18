import csv
import json
import tempfile
import unittest
from pathlib import Path
from hub.v6.evaluate import evaluate
from hub.v6.offline import packet

class EvaluationTests(unittest.TestCase):
    def test_blank_and_automated_labels_cannot_be_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'pairs.csv';r=Path(tmp)/'relevance.csv'
            p.write_text('report_id,pair_id,left,right,label,annotator,provenance\na,x,u,v,same_event,model,model\n')
            r.write_text('event_id,relevant,annotator,provenance\n')
            result=evaluate({'report_id':'a','items':[]},p,r)
            self.assertEqual(result['status'],'blocked_pending_human_labels')
            self.assertIsNone(result['precision']);self.assertIsNone(result['p_at_10'])
    def test_packet_preserves_labels_and_refuses_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            items=[{'url':f'https://example.org/{i}','title':'Some paper','fingerprint':str(i)} for i in range(160)]
            report={'report_id':'a','items':items,'pairs':[],'scores':[{'event_id':str(i),'members':[x['url']]} for i,x in enumerate(items)]}
            packet(report,out)
            with (out/'pair-labels.csv').open() as f:
                pairs=list(csv.DictReader(f))
            self.assertEqual(len({r[k] for r in pairs for k in ('left','right')}),160)
            pairs[0]['label']='different_event';pairs[0]['annotator']='test reviewer';pairs[0]['provenance']='human'
            with (out/'pair-labels.csv').open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=pairs[0]);w.writeheader();w.writerows(pairs)
            before=(out/'pair-labels.csv').read_text();packet(report,out)
            self.assertEqual(before,(out/'pair-labels.csv').read_text())
            with self.assertRaises(ValueError):packet({**report,'report_id':'b'},out)
            self.assertEqual(before,(out/'pair-labels.csv').read_text())
