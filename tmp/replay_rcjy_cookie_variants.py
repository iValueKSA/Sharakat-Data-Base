import json,httpx
x=json.load(open('/tmp/rcjy_browser_session.json'))
base={c['name']:c['value'] for c in x['cookies']}
headers={k:v for k,v in x['req']['headers'].items() if k.lower() not in {'content-length','host','connection','accept-encoding','cookie'}}
sets=[set(base),set(base)-{'osVisit'},set(base)-{'osVisitor'},set(base)-{'nr1InvestmentPortal'},set(base)-{'nr2InvestmentPortal'}, {'AL_SESS-S','AL_BALANCE-S'}, {'osVisit','osVisitor','nr1InvestmentPortal','nr2InvestmentPortal'}]
for names in sets:
 try:
  with httpx.Client() as c:
   r=c.post(x['req']['url'],headers=headers,cookies={k:v for k,v in base.items() if k in names},content=x['req']['postData'],timeout=20)
   print(sorted(names),r.status_code,r.headers.get('content-type'))
 except Exception as e:print(sorted(names),type(e).__name__)
