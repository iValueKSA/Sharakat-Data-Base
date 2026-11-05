const fs=require('fs'); const p='tmp/verify_complete_sector_classification_live.cjs'; let s=fs.readFileSync(p,'utf8');
s=s.replace('barCount:document.querySelectorAll(\'#rdSectorChart .rd-column\').length,unspecified:', 'barCount:document.querySelectorAll(\'#rdSectorChart .rd-column\').length,represented:[...document.querySelectorAll(\'#rdSectorChart .rd-column\')].flatMap(el=>el.dataset.dashValue?[el.dataset.dashValue]:(el.dataset.dashValues?JSON.parse(el.dataset.dashValues):[])),unspecified:');
fs.writeFileSync(p,s);
