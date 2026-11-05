import asyncio,csv,io,json
from collections import Counter
from openpyxl import load_workbook
from sqlalchemy import select,func,text
from app.database import SessionLocal
from app.models import Opportunity
from app.standardization import canonical_id,canonical_value
from app import main as api

db=SessionLocal();db.execute(text('SET TRANSACTION READ ONLY'))
try:
 masters=db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None))).all()
 db_counts=Counter(canonical_id('sector',m.sector) for m in masters)
 dashboard=api.data_dashboard()
 chart={r['canonical_id']:int(r['count']) for r in dashboard.get('by_sector',[])}
 chart_labels={r['canonical_id']:r['name'] for r in dashboard.get('by_sector',[])}
 api_filters={}
 for sector_id,expected in chart.items():
  response=api.opportunities(sector=sector_id,limit=500,offset=0)
  labels=[r['sector'] for r in response.get('items',[])]
  api_filters[sector_id]={'total':int(response['total']),'rows':len(labels),'canonical_labels':sorted(set(labels)),'expected_label':chart_labels[sector_id],'exact':int(response['total'])==expected and all(x==chart_labels[sector_id] for x in labels)}
 csv_response=api.export_csv()
 async def body(resp):
  parts=[]
  async for x in resp.body_iterator: parts.append(x if isinstance(x,bytes) else str(x).encode())
  return b''.join(parts)
 csv_text=asyncio.run(body(csv_response)).decode('utf-8-sig')
 csv_rows=list(csv.reader(io.StringIO(csv_text)))
 csv_header=csv_rows[0]
 csv_sector_index=next(i for i,x in enumerate(csv_header) if 'قطاع' in str(x) or 'sector' in str(x).casefold())
 csv_counts=Counter(canonical_id('sector',r[csv_sector_index]) for r in csv_rows[1:] if len(r)>csv_sector_index)
 xlsx_response=api.export_xlsx()
 wb=load_workbook(io.BytesIO(xlsx_response.body),read_only=True,data_only=True)
 ws=wb['الفرص الاستثمارية']
 header_row=None; sector_col=None
 for ridx,row in enumerate(ws.iter_rows(min_row=1,max_row=12,values_only=True),1):
  for cidx,v in enumerate(row):
   if 'قطاع' in str(v or '') or 'sector' in str(v or '').casefold(): header_row=ridx;sector_col=cidx+1;break
  if sector_col: break
 xlsx_counts=Counter(canonical_id('sector',row[sector_col-1]) for row in ws.iter_rows(min_row=header_row+1,values_only=True) if len(row)>=sector_col and row[sector_col-1])
 wb.close()
 summary={'current_masters':len(masters),'database_counts':dict(db_counts),'dashboard_total':dashboard['global_total'],'dashboard_sector_counts':chart,'api_sector_filters':api_filters,'csv':{'rows':len(csv_rows)-1,'sector_header':csv_header[csv_sector_index],'counts':dict(csv_counts),'matches_database':csv_counts==db_counts},'xlsx':{'rows':sum(xlsx_counts.values()),'header_row':header_row,'sector_column':sector_col,'counts':dict(xlsx_counts),'matches_database':xlsx_counts==db_counts},'dashboard_sector_total':sum(chart.values()),'all_match':len(masters)==dashboard['global_total']==sum(chart.values()) and db_counts==Counter(chart)==csv_counts==xlsx_counts and all(x['exact'] for x in api_filters.values())}
 with open('/tmp/sector-dashboard-reconciliation.json','w',encoding='utf-8') as f: json.dump(summary,f,ensure_ascii=False,indent=2)
 print(json.dumps(summary,ensure_ascii=False,indent=2))
finally: db.close()

