from decimal import Decimal
from app.values import number
from app.reasons import reject,sources
from app.errors import DomainError
def evaluate(rows,context):
    """本期承接：已签项目增量 = 各分项归属合计 + 未归属余量。

    项目级行（item=PROJECT，M2分流）给出本期签出总量；分项行必须已过变更定版与
    累计还原，自带变更依据与前期已签量。余量显式挂账，不摊派、不吞没；
    全部期间对平（余量为零）时 metrics.reconciled 才为真。
    """
    params=context.get("parameters",{});overrides=params.get("previous_revisions",{})
    project=(context.get("billitems") or {}).get("project_rows",[])
    bad=[];levels={}
    for row in sorted(project,key=lambda x:(x["period"],x["claim_id"])):
        period=row["period"]
        if period in levels:bad.append(reject(row,"PROJECT_PERIOD_DUPLICATE","同周期项目级累计重复申报"));continue
        prev=number(overrides.get(row["claim_id"],row["previous_qty"]));current=number(row["cumulative_qty"])
        if prev<0:raise DomainError("BAD_PREVIOUS","前审累计量不能为负")
        increment=current-prev
        if increment<0 and row.get("reversal")!="approved":bad.append(reject(row,"REVERSAL_REQUIRED","负进度缺少已批冲回凭证"));continue
        levels[period]={"signed":increment,"row":row}
    attribution={}
    for row in rows:attribution.setdefault(row["period"],[]).append(row)
    out=[]
    for period in sorted(levels):
        signed=levels[period]["signed"]
        items=sorted(attribution.get(period,[]),key=lambda x:(x["item"],x["claim_id"]))
        attributed=sum((number(r["increment_qty"]) for r in items),Decimal(0))
        remainder=signed-attributed
        out.append({"kind":"项目承接","period":period,"signed_increment":str(signed),"attributed":str(attributed),"remainder":str(remainder),"reconciled":"对平" if remainder==0 else "未对平","_sources":sources(levels[period]["row"])})
        for r in items:
            out.append({"kind":"分项归属","period":period,"item":r["item"],"increment_qty":str(number(r["increment_qty"])),"approved_change":r.get("approved_change",""),"approved_previous":r.get("approved_previous",""),"_sources":sources(r)})
    summaries=[r for r in out if r["kind"]=="项目承接"]
    pending=[r["period"] for r in summaries if r["reconciled"]=="未对平"]
    metrics={"periods":len(summaries),"signed_total":str(sum((number(r["signed_increment"]) for r in summaries),Decimal(0))),"attributed_total":str(sum((number(r["attributed"]) for r in summaries),Decimal(0))),"remainder_total":str(sum((number(r["remainder"]) for r in summaries),Decimal(0))),"reconciled":not pending,"pending":pending}
    if params.get("cumulative_version") is not None:metrics["cumulative_version"]=str(params["cumulative_version"])
    return {"rows":out,"quarantine":bad,"metrics":metrics}
