"""Read-only preview for migration 0022; does not modify the database."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.status_lifecycle import canonical_source_status, aggregate_master_status
from app.database import engine as application_engine


def main():
    source_states=Counter(); by_source=defaultdict(Counter); corrections=[]; conflicts=[]; source_rows=[]
    with Session(application_engine) as db:
        masters=db.execute(text("select id, status from opportunities where merged_into_id is null order by id")).all()
        rows=db.execute(text("""
            select so.id,so.master_opportunity_id,so.raw_status,so.raw_dates,so.source_opportunity_id,
                   so.missing_successful_checks,so.source_url,s.source_key,s.missing_confirmation_threshold
            from source_opportunities so join sources s on s.id=so.source_id order by so.id
        """)).mappings().all()
        derived={}
        for row in rows:
            dates=row["raw_dates"] if isinstance(row["raw_dates"],dict) else {}
            if (row["missing_successful_checks"] or 0)>=max(1,int(row["missing_confirmation_threshold"] or 3)):
                status="أزيلت من المصدر";flags=[]
            else:
                status,flags=canonical_source_status(row["source_key"],row["raw_status"],dates.get("deadline"))
            derived[row["id"]]=status
            source_states[status]+=1;by_source[row["source_key"]][status]+=1
            if row["master_opportunity_id"] is not None:
                source_rows.append((row["master_opportunity_id"],status,row["id"],flags))
        by_master=defaultdict(list)
        for master_id,status,row_id,flags in source_rows:
            by_master[master_id].append((status,row_id,flags))
        for master_id,before in masters:
            linked=by_master.get(master_id,[])
            after,flags=aggregate_master_status([status for status,_,_ in linked])
            if before!=after:
                corrections.append({"master_id":master_id,"before":before,"after":after,
                    "source_record_ids":[row_id for _,row_id,_ in linked],"source_states":[status for status,_,_ in linked]})
            if flags:
                conflicts.append({"master_id":master_id,"master_status":after,"source_states":[status for status,_,_ in linked],"flags":flags,
                    "source_record_ids":[row_id for _,row_id,_ in linked]})
        raw_values=Counter((row["source_key"],row["raw_status"]) for row in rows)
        cancellations=[{"id":row["id"],"source":row["source_key"],"raw_status":row["raw_status"]}
            for row in rows if any(term in str(row["raw_status"] or "").lower() for term in ("cancel","ملغ"))]
        print(json.dumps({"previewed_at":datetime.now().astimezone().isoformat(),
            "master_count":len(masters),"source_record_count":len(rows),"masters_without_linked_source":sum(1 for master_id,_ in masters if not by_master.get(master_id)),
            "source_status_counts":dict(source_states),"source_status_counts_by_source":{key:dict(value) for key,value in by_source.items()},
            "raw_status_values":[{"source":key,"raw_status":status,"count":count} for (key,status),count in raw_values.items()],
            "master_corrections":corrections,"master_correction_count":len(corrections),"multi_source_status_conflicts":conflicts,
            "cancellation_evidence_candidates":cancellations},ensure_ascii=False,indent=2,default=str))


if __name__=="__main__":main()
