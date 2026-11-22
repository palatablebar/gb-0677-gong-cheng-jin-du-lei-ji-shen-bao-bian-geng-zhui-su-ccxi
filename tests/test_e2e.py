import csv,io
from app.pipeline import execute,load_sample
from app import store
def test_full_sample_flow(client):
    r=client.post("/api/runs",json={"sample":"dirty.csv"});assert r.status_code==200
    p=r.get_json();assert len(p["stages"])==8
    assert p["stages"][5]["metrics"]["balanced"] is True
def test_idempotent_real_input(sample):
    a=execute(sample);b=execute(sample)
    assert a["run_id"]==b["run_id"] and len(store.history())==1
def test_stale_review_409(client):
    "TRAP-26 陈旧复核不得覆盖新版本"
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json();u="/api/runs/"+p["run_id"]+"/review"
    assert client.post(u,json={"version":1,"decision":"已复核"}).status_code==200
    assert client.post(u,json={"version":1,"decision":"退回复核"}).status_code==409
def test_export_has_manifest_and_quarantine(client):
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    r=client.get("/api/runs/"+p["run_id"]+"/archive")
    rows=list(csv.reader(io.StringIO(r.data.decode("utf-8-sig"))))
    assert rows[0][1]=="input_sha256" and any(x[3]=="quarantine" for x in rows[1:])
def test_failed_import_is_atomic(client):
    assert client.post("/api/runs",json={"csv":"bad"}).status_code==422
    assert store.history()==[]
def test_module_entrances(client):
    from app.config import MODULES
    for slug,name in MODULES:
        assert client.get("/api/"+slug).status_code==200
        assert client.get("/"+slug).status_code==200
def test_missing_run_404(client): assert client.get("/api/runs/missing").status_code==404
BALANCED_CSV="claim_id,item,period,cumulative_qty,previous_qty,change_id,reversal,reported,note\nP1,项目级,2026-11,125,100,,none,0.00,项目级\nA1,钢筋,2026-11,125,100,C0,none,2125.00,分项\n"
def test_unreconciled_carryover_blocks_signoff(client):
    "项目累计与分项归属未对平，不能正式签认"
    p=client.post("/api/runs",json={"sample":"mixed.csv"}).get_json()
    assert p["stages"][6]["metrics"]["reconciled"] is False
    r=client.post("/api/runs/"+p["run_id"]+"/review",json={"version":1,"decision":"已复核"})
    assert r.status_code==409 and r.get_json()["code"]=="UNRECONCILED"
    assert client.post("/api/runs/"+p["run_id"]+"/review",json={"version":1,"decision":"退回复核"}).status_code==200
def test_reconciled_carryover_allows_signoff(client):
    p=client.post("/api/runs",json={"csv":BALANCED_CSV}).get_json()
    assert p["stages"][6]["metrics"]["reconciled"] is True
    assert client.post("/api/runs/"+p["run_id"]+"/review",json={"version":1,"decision":"已复核"}).status_code==200
def test_failed_switch_keeps_previous_result(client):
    "切换失败时保留上一版结果"
    p=client.post("/api/runs",json={"sample":"mixed.csv"}).get_json()
    assert client.post("/api/runs",json={"csv":"bad"}).status_code==422
    assert store.latest()["run_id"]==p["run_id"] and len(store.history())==1
    assert client.get("/carryover").status_code==200
def test_same_cumulative_version_rerun_adds_no_increment(client):
    "同一累计版本重跑不得新增本期增量"
    body={"sample":"mixed.csv","parameters":{"cumulative_version":"2026-11"}}
    a=client.post("/api/runs",json=body).get_json();b=client.post("/api/runs",json=body).get_json()
    assert a["run_id"]==b["run_id"] and len(store.history())==1
    assert b["stages"][6]["metrics"]["signed_total"]=="85" and b["stages"][6]["metrics"]["cumulative_version"]=="2026-11"
