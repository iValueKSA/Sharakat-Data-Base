import os,uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from sqlalchemy import create_engine,select,text,func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app import main
from app.models import Base,Opportunity,Source,SourceOpportunity,OpportunityConflict,AuditEvent
schema='rg_test_'+uuid.uuid4().hex[:12]
url=make_url(os.environ['DATABASE_URL'])
admin_engine=create_engine(url,pool_pre_ping=True)
with admin_engine.begin() as c:c.execute(text(f'CREATE SCHEMA {schema}'))
test_engine=create_engine(url,connect_args={'options':f'-csearch_path={schema}'},pool_pre_ping=True)
Factory=sessionmaker(bind=test_engine,expire_on_commit=False)
try:
 Base.metadata.create_all(test_engine)
 now=datetime.now(timezone.utc)
 with Factory() as db:
  source=Source(source_key='fixture',source_name_ar='مصدر اختبار',organization_name='fixture',base_url='https://example.test',opportunities_url='https://example.test',priority=1);db.add(source);db.flush()
  master=Opportunity(canonical_id='CONCURRENT-1',title_ar='اختبار تنافس القرار',normalized_title='اختبار تنافس القرار',primary_publication_platform='مصدر اختبار',city='الأحساء',status='منشورة',location_confidence_score=.9,location_detection_method='fixture',location_evidence='fixture',data_quality_score=.9,manual_review_required=False,first_seen_at=now,last_seen_at=now,last_updated_at=now,created_at=now,updated_at=now);db.add(master);db.flush()
  record=SourceOpportunity(source_id=source.id,master_opportunity_id=master.id,source_opportunity_id='fixture-1',source_title=master.title_ar,normalized_source_title=master.title_ar,source_url='https://example.test/1',canonical_status='منشورة',raw_data_json={'fixture':True},raw_dates={},first_seen_at=now,last_seen_at=now,content_hash='f'*64,parser_version='fixture');db.add(record);db.flush()
  case=OpportunityConflict(opportunity_id=master.id,field_name='sector',conflict_type='FIELD_VALUE_CONFLICT',selected_value='تجاري',conflicting_value='صناعي',source_id=source.id,source_record_id=record.id,detected_at=now,status='OPEN');db.add(case);db.commit();case_id=case.id
 os.environ['ADMIN_TOKEN']='review-concurrency-fixture'
 main.SessionLocal=Factory
 barrier=__import__('threading').Barrier(2)
 def decide():
  client=TestClient(main.app,raise_server_exceptions=False);barrier.wait()
  try:return client.post(f'/api/admin/conflicts/{case_id}/use_source',headers={'X-Admin-Token':'review-concurrency-fixture'},json={'note':'Concurrent fixture resolution evidence is sufficiently described.'}).status_code
  finally:client.close()
 with ThreadPoolExecutor(max_workers=2) as pool: statuses=sorted(pool.map(lambda _:decide(),range(2)))
 with Factory() as db:
  case=db.get(OpportunityConflict,case_id);master=db.get(Opportunity,case.opportunity_id);record=db.get(SourceOpportunity,case.source_record_id)
  audit_count=db.scalar(select(func.count(AuditEvent.id)).where(AuditEvent.entity_type=='opportunity_conflict',AuditEvent.entity_id==str(case_id)))
  assert statuses==[200,409],statuses
  assert case.status=='RESOLVED_SOURCE' and master.sector=='صناعي' and record.raw_data_json=={'fixture':True} and audit_count==1
 print({'temporary_postgres_schema':schema,'concurrent_response_statuses':statuses,'one_resolution_and_audit':True,'raw_payload_preserved':True})
finally:
 test_engine.dispose()
 with admin_engine.begin() as c:c.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
 admin_engine.dispose()

