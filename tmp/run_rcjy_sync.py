import asyncio, json
from app.service import sync_source
result=asyncio.run(sync_source('rcjy-investment-opportunities'))
print(json.dumps(result,ensure_ascii=False,default=str))
