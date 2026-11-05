import urllib.request,csv,io,json,openpyxl
base='http://host.docker.internal:8080'
def get(path):
 with urllib.request.urlopen(base+path,timeout=30) as r:return r.status,r.headers, r.read()
status,h,b=get('/api/opportunities?limit=500'); data=json.loads(b)
cs,_,cb=get('/api/export.csv'); rows=list(csv.reader(io.StringIO(cb.decode('utf-8-sig'))))
xs,xh,xb=get('/api/export.xlsx'); wb=openpyxl.load_workbook(io.BytesIO(xb),read_only=True,data_only=True); ws=wb.active; allrows=list(ws.iter_rows(values_only=True)); header=next((i for i,row in enumerate(allrows) if row and row[0]=='اسم الفرصة'),None); xcount=sum(1 for row in allrows[header+1:] if row and row[0] not in (None,'')) if header is not None else None
out={'api_status':status,'api_total':data['total'],'api_unique_master_ids':len(set(x['id'] for x in data['items'])),'csv_status':cs,'csv_data_rows':len(rows)-1,'csv_header_columns':len(rows[0]),'xlsx_status':xs,'xlsx_data_rows':xcount,'xlsx_total_rows':len(allrows),'xlsx_header_row_index_zero_based':header,'xlsx_mime':xh.get_content_type(),'xlsx_bytes':len(xb)}
print(json.dumps(out,ensure_ascii=False));wb.close()
