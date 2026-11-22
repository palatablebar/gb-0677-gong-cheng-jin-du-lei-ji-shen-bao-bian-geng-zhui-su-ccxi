import pytest
from app.pipeline import calculate,load_sample
from app.modules.m7_carryover.rules import evaluate
from app.errors import DomainError
@pytest.fixture
def mixed(): return calculate(load_sample("mixed.csv"))
def stage(mixed): return mixed["stages"][6]
def summaries(mixed): return [r for r in stage(mixed)["rows"] if r["kind"]=="项目承接"]
def attributions(mixed): return [r for r in stage(mixed)["rows"] if r["kind"]=="分项归属"]
def test_carryover_identity_holds(mixed):
    "已签项目增量 = 分项归属合计 + 未归属余量"
    for row in summaries(mixed): assert float(row["signed_increment"])==float(row["attributed"])+float(row["remainder"])
def test_reconciled_period_balances(mixed):
    row=next(r for r in summaries(mixed) if r["period"]=="2026-10")
    assert row["signed_increment"]=="40" and row["remainder"]=="0" and row["reconciled"]=="对平"
def test_unattributed_remainder_is_explicit(mixed):
    row=next(r for r in summaries(mixed) if r["period"]=="2026-11")
    assert row["signed_increment"]=="45" and row["attributed"]=="30" and row["remainder"]=="15" and row["reconciled"]=="未对平"
    assert stage(mixed)["metrics"]["reconciled"] is False and stage(mixed)["metrics"]["pending"]==["2026-11"]
def test_attribution_carries_change_and_previous(mixed):
    row=next(r for r in attributions(mixed) if r["item"]=="001" and r["period"]=="2026-11")
    assert row["approved_change"]=="C1" and row["approved_previous"]=="130" and row["increment_qty"]=="15"
def test_project_rows_diverted_from_money_pipeline(mixed):
    assert mixed["stages"][1]["metrics"]["project_rows"]==2
    assert all(r["item"]!="PROJECT" for r in mixed["stages"][5]["rows"])
    assert mixed["stages"][5]["metrics"]["balanced"] is True and mixed["stages"][5]["metrics"]["project_inputs"]==2
def valuation_row(period="2026-11",item="001",increment="25"):
    return {"claim_id":"A","item":item,"period":period,"increment_qty":increment,"approved_change":"C0","approved_previous":"100","_sources":[1]}
def project_row(period="2026-11",current="125",previous="100",claim="P1",reversal="none"):
    return {"claim_id":claim,"item":"PROJECT","period":period,"cumulative_qty":current,"previous_qty":previous,"reversal":reversal,"_sources":[2]}
def context(project_rows): return {"parameters":{},"billitems":{"project_rows":project_rows}}
def test_no_project_rows_means_no_carryover():
    r=evaluate([valuation_row()],context([]));assert r["rows"]==[] and r["metrics"]["reconciled"] is True and r["metrics"]["periods"]==0
def test_duplicate_project_period_quarantined():
    r=evaluate([],context([project_row(claim="P1"),project_row(claim="P2")]))
    assert r["quarantine"][0]["reason"]=="PROJECT_PERIOD_DUPLICATE"
def test_negative_project_increment_requires_reversal():
    r=evaluate([],context([project_row(current="90")]));assert r["quarantine"][0]["reason"]=="REVERSAL_REQUIRED"
def test_approved_project_reversal():
    r=evaluate([],context([project_row(current="90",reversal="approved")]))
    assert r["rows"][0]["signed_increment"]=="-10" and r["rows"][0]["remainder"]=="-10"
def test_previous_revision_applies_to_project_level():
    ctx=context([project_row()]);ctx["parameters"]={"previous_revisions":{"P1":"110"}}
    assert evaluate([valuation_row()],ctx)["rows"][0]["signed_increment"]=="15"
def test_cumulative_version_recorded():
    ctx=context([project_row()]);ctx["parameters"]={"cumulative_version":"2026-11"}
    assert evaluate([],ctx)["metrics"]["cumulative_version"]=="2026-11"
def test_negative_previous_rejected():
    with pytest.raises(DomainError): evaluate([],context([project_row(previous="-1")]))
