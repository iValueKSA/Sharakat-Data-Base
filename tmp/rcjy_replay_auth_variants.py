import json,httpx,random,time
x=json.load(open('/tmp/rcjy_browser_session.json'))
for csrf_mode in ['captured','none','random']:
 for token_mode in ['captured','timestamp']:
  with httpx.Client(follow_redirects=True,timeout=20) as c:
   page=c.get('https://invest.rcjy.gov.sa/InvestmentPortal/InvestmentOpportunities')
   hh={k:v for k,v in x['req']['headers'].items() if k.lower() not in {'content-length','host','connection','accept-encoding','cookie'}}
   if csrf_mode=='none':hh.pop('x-csrftoken',None)
   elif csrf_mode=='random':hh['x-csrftoken']=''.join(random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/') for _ in range(24))+'='
   if token_mode=='timestamp':hh['outsystems-request-token']=str(int(time.time()*1000))
   r=c.post(x['req']['url'],headers=hh,content=x['req']['postData'])
   print(csrf_mode,token_mode,r.status_code,r.headers.get('content-type'))
