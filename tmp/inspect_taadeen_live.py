import httpx,re
u='https://cms.taadeen.sa/en/mining-bids'
r=httpx.get(u,timeout=30,headers={'User-Agent':'Mozilla/5.0'})
print('status',r.status_code,'bytes',len(r.content),'final',r.url)
open('tmp/taadeen-live-listing.html','w',encoding='utf-8').write(r.text)
for x in re.findall(r'<script[^>]+src=["\']([^"\']+)',r.text): print('SCRIPT',x)
for pat in ['Round 9','Round 10','pagination','api/','__NEXT_DATA__','Mining Bids']:
 print('MATCH',pat, r.text.find(pat))
print('hrefs',len(re.findall(r'href=',r.text,re.I)))
