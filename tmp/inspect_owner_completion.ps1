$rows=Get-Content docs\validation\data\owner-completion\target-evidence-inventory.jsonl|ForEach-Object {$_|ConvertFrom-Json}
$dist=foreach($src in @('alahsa-opportunities','ahda','invest-saudi','ncp')){$entries=@($rows|Where-Object {@($_.sources.source_key)-contains $src});[pscustomobject]@{source=$src;master_count=$entries.Count;master_ids=($entries.master_id -join ',')}}
$dist|ConvertTo-Json -Depth 4
$out=@()
foreach($m in $rows){foreach($r in @($m.sources)){if($r.source_key -eq 'invest-saudi'){$raw=$r.raw_data_json;$lines=@($raw.description -split '[\r\n]+'|Where-Object {$_ -match '(وزارة|هيئة|أمانة|بلدية|جامعة|شركة|authority|ministry|municipality|university|company|entity|developer|owner|operat)'});$out += [pscustomobject]@{master=$m.master_id;record=$r.source_record_id;title=$r.source_title;adapter_owner=$r.source_owner;backed_by=$raw.backed_by;contacts=($raw.contact_details|ConvertTo-Json -Compress);inner_data=($raw.inner_data|ConvertTo-Json -Compress);entities_in_description=($lines -join ' | ')}}}}
$out|ConvertTo-Json -Depth 5
