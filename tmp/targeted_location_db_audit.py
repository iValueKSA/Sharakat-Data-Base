from sqlalchemy import select,func,text
from sqlalchemy.orm import Session
from app.database import engine
from app.models import SourceOpportunity,Source,LocationReview,Opportunity
ids={283,466,601,671,1038,1166,1167,2358,2359,2360,2361,2362}
with engine.connect().execution_options(isolation_level='REPEATABLE READ') as c:
 t=c.begin();c.execute(text('SET TRANSACTION READ ONLY'))
 rows=c.execute(text('''SELECT so.id,so.source_opportunity_id,so.source_reference_number,so.master_opportunity_id,so.raw_location,so.source_title,so.raw_data_json->>'qualified_location' AS qualified,so.raw_data_json->>'location_confidence_score' AS confidence,so.raw_data_json->>'location_detection_method' AS method,lr.id AS review_id,lr.status AS review_status,lr.reason AS review_reason,lr.evidence AS review_evidence FROM source_opportunities so JOIN sources s ON s.id=so.source_id LEFT JOIN location_reviews lr ON lr.source_id=so.source_id AND lr.external_id=so.source_opportunity_id WHERE s.source_key='invest-saudi' AND so.id=ANY(:ids) ORDER BY so.id'''),{'ids':list(ids)}).mappings().all()
 print('TARGETS')
 for r in rows:print(dict(r))
 print('QUALIFIED_COUNTS',dict(c.execute(text('''SELECT count(*) total, count(*) FILTER (WHERE master_opportunity_id IS NOT NULL) linked, count(*) FILTER (WHERE master_opportunity_id IS NULL) unlinked FROM source_opportunities WHERE coalesce((raw_data_json->>'qualified_location')::boolean,false)=true''')).mappings().one()))
 print('LOCATION_REVIEW_STATUSES', [dict(x) for x in c.execute(text('SELECT status,count(*) AS count FROM location_reviews GROUP BY status ORDER BY status')).mappings().all()])
 print('SOURCE COUNTS', [dict(x) for x in c.execute(text('''SELECT s.source_key,count(*) total,count(*) FILTER (WHERE so.master_opportunity_id IS NOT NULL) linked,count(*) FILTER (WHERE coalesce((so.raw_data_json->>'qualified_location')::boolean,false)) qualified FROM sources s LEFT JOIN source_opportunities so ON so.source_id=s.id GROUP BY s.source_key ORDER BY s.source_key''')).mappings().all()])
 print('CURRENT_MASTER_NO_SOURCE', c.scalar(text('''SELECT count(*) FROM opportunities o WHERE o.merged_into_id IS NULL AND NOT EXISTS (SELECT 1 FROM source_opportunities so WHERE so.master_opportunity_id=o.id)''')))
 t.rollback()
