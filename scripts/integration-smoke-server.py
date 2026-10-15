"""Synthetic browser smoke fixture. Never connects to production or imports user data."""
import datetime as dt
import os
from pathlib import Path
import sys
import tempfile
from werkzeug.security import generate_password_hash

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from hub.app import create_app, ingest

def main():
    folder=tempfile.TemporaryDirectory(prefix="yanhaoo-browser-")
    database=str(Path(folder.name)/"fixture.sqlite")
    app=create_app({
        "PUBLIC":True,"TESTING":True,"DB":database,
        "SECRET_KEY":"test-integration-browser-key-not-for-production",
        "PASSWORD_HASH":generate_password_hash("browser-test-password"),
        "INGEST_TOKEN":"browser-only-ingest-token",
        "SESSION_COOKIE_SECURE":False,
        "TRUST_PROXY":False
    })
    ingest(database,{"schema":1,"items":[
      {
        "id":"browser-reviewed-harness","title":"Harness 成本优化完整解析","url":"https://example.org/harness",
        "source":"Synthetic Source A","topic":"agent","published_at":"2026-10-14",
        "collected_at":"2026-10-15T01:00:00+00:00","summary":"合成核验精选样例",
        "verification_status":"reviewed","scope":"合成测试样本",
        "verification_notes":"测试用的人工核验边界","learning_value":"Agent 架构优化学习",
        "evidence":[{"url":"https://example.org/harness","label":"合成样例","supports":"样例文字"}],
      },
      {
        "id":"browser-candidate-rna","title":"RNA 生物学论文线索","url":"https://arxiv.org/abs/2610.99999",
        "source":"Synthetic Source B","topic":"research","published_at":"2026-10-13",
        "collected_at":"2026-10-15T01:00:00+00:00",
        "summary":"合成待核验候选内容","verification_status":"candidate",
        "expires_at":"2099-01-01T00:00:00+00:00"
      }
    ]})
    port=int(os.environ.get("SMOKE_PORT","8765"))
    app.run(host="127.0.0.1",port=port,use_reloader=False,threaded=True)

if __name__=="__main__":
    main()
