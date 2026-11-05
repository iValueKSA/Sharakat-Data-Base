import os,hashlib,json,redis
r=redis.Redis.from_url(os.environ['REDIS_URL'])
keys=['rate:login:'+hashlib.sha256(('testclient:'+u).encode()).hexdigest() for u in ('admin@example.test','analyst@example.test','viewer@example.test')]
print(json.dumps({'test_scoped_keys_deleted':r.delete(*keys),'remaining':sum(r.exists(k) for k in keys)}))