from pathlib import Path
from pypdf import PdfReader
for p in sorted(Path('tmp/pdfs').glob('*.pdf')):
 r=PdfReader(p); text='\n'.join(x.extract_text() or '' for x in r.pages)
 out=Path(str(p)+'.txt');out.write_text(text,encoding='utf-8')
 print(f'### {p.name} pages={len(r.pages)} chars={len(text)}')
 print(text[:4800])
