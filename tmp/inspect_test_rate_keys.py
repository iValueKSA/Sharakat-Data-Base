import os,hashlib,json,redis
r=redis.Redis.from_url(os.environ['REDIS_URL'])
keys=[]
for user in ('admin@example.test','analyst@example.test','viewer@example.test'):
 raw='testclient:'+user;keys.append(('rate:login:'+hashlib.sha256(raw.encode()).hexdigest(),raw))
for path in ('/api/export.csv','/api/export.xlsx','/api/admin/users','/api/admin/conflicts/999/keep'):
 raw='testclient:'+path;keys.append(('rate:api:'+hashlib.sha256(raw.encode()).hexdigest(),raw))
print(json.dumps([{'key':k,'test_input':raw,'value':r.get(k).decode() if r.get(k) else None,'ttl':r.ttl(k)} for k,raw in keys if r.exists(k)]))