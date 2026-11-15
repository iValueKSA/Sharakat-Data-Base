import csv,json,sys
from pathlib import Path
from datetime import datetime,timezone
from fastapi.testclient import TestClient
import app.main as main
regpath,preflightpath,alahsabeforepath,outpath=map(Path,sys.argv[1:5])
with regpath.open(encoding='utf-8-sig',newline='') as f: reg=list(csv.DictReader(f))
pre=json.loads(preflightpath.read_text(encoding='utf-8')); alahsa_before=json.loads(alahsabeforepath.read_text(encoding='utf-8'))
targets={int(x['master_id']) for x in reg}
client=TestClient(main.app,raise_server_exceptions=True)
def fetch(url):
 r=client.get(url)
 return r.status_code,r.json()
ns,n=fetch('/api/data-dashboard/geography')
as_,a=fetch('/api/data-dashboard/geography?governorate_id=501')
def flat(p):return [int(i) for q in p.get('points',[]) for i in q.get('ids',[])]
n_ids=flat(n);a_ids=flat(a);prev=set(map(int,alahsa_before['unique_master_ids']))
checks={'national_http_200':ns==200 and n.get('map_scope')=='NATIONAL','alahsa_http_200':as_==200 and a.get('map_scope')=='NATIONAL','national_total_6309':n.get('counts',{}).get('exact_mapped')==6309,'alahsa_total_447':a.get('counts',{}).get('exact_mapped')==447,'all_302_present_national':targets<=set(n_ids),'all_302_present_alahsa':targets<=set(a_ids),'old_145_preserved_alahsa':prev<=set(a_ids),'national_ids_unique':len(n_ids)==len(set(n_ids)),'alahsa_ids_unique':len(a_ids)==len(set(a_ids)),'national_preflight_other_governorates_unchanged':bool(pre.get('passed'))}
result={'captured_at_utc':datetime.now(timezone.utc).isoformat(),'mode':'API_VERIFICATION_AFTER_EXACT_TRANSACTION_SQL_ON_ISOLATED_RESTORED_SNAPSHOT','checks':checks,'passed':all(checks.values()),'national':{'http_status':ns,'counts':n.get('counts'),'flat_ids':len(n_ids),'unique_ids':len(set(n_ids)),'added_vs_preflight':len(set(n_ids)-set(map(int,pre['baseline_api']['unique_ids'])))},'alahsa':{'http_status':as_,'counts':a.get('counts'),'flat_ids':len(a_ids),'unique_ids':len(set(a_ids)),'added_vs_live_baseline':len(set(a_ids)-prev)},'target_count':len(targets)}
outpath.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
sys.exit(0 if result['passed'] else 2)