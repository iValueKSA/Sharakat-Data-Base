import hashlib, json
from collections import Counter
from datetime import datetime, timezone
from app.database import SessionLocal
from app.models import Opportunity, SourceOpportunity, SourceObservation

def digest(value):
    payload=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode()
    return hashlib.sha256(payload).hexdigest()
with SessionLocal() as db:
    masters=db.query(Opportunity).order_by(Opportunity.id).all()
    sources=db.query(SourceOpportunity).order_by(SourceOpportunity.id).all()
    observations=db.query(SourceObservation.id,SourceObservation.source_opportunity_id).all()
    obs_counts=Counter(source_id for _,source_id in observations)
    doc={"captured_at":datetime.now(timezone.utc).isoformat(),"total_master_rows":len(masters),
      "master_rows":[{"id":m.id,"canonical_id":m.canonical_id,"merged_into_id":m.merged_into_id,"status":m.status} for m in masters],
      "source_rows_count":len(sources),"source_rows":[{"id":s.id,"source_id":s.source_id,"source_key":s.source.source_key,"master_id":s.master_opportunity_id,"external_id":s.source_opportunity_id,"source_url_sha256":hashlib.sha256((s.source_url or "").encode()).hexdigest(),"raw_payload_sha256":digest(s.raw_data_json or {}),"source_status":s.canonical_status,"missing_checks":s.missing_successful_checks,"observation_count":obs_counts[s.id]} for s in sources],
      "observations_count":len(observations),"master_id_digest":digest([(m.id,m.canonical_id,m.merged_into_id) for m in masters]),"source_link_digest":digest([(s.id,s.source_id,s.master_opportunity_id,s.source_opportunity_id) for s in sources]),"raw_payload_digest":digest([(s.id,digest(s.raw_data_json or {})) for s in sources]),"source_url_digest":digest([(s.id,hashlib.sha256((s.source_url or "").encode()).hexdigest()) for s in sources]),"lifecycle_digest":digest([(s.id,s.canonical_status,s.missing_successful_checks) for s in sources]+[(m.id,m.status) for m in masters]),"observation_ids_digest":digest([id for id,_ in observations])}
    print(json.dumps(doc,ensure_ascii=False))
