import csv, json, sys, types
from pathlib import Path
import app.main as main

current_path, api_path, decisions_path, output_path = map(Path, sys.argv[1:5])
current = json.loads(current_path.read_text(encoding='utf-8'))
api = json.loads(api_path.read_text(encoding='utf-8'))
with decisions_path.open(encoding='utf-8-sig', newline='') as f:
    decisions = list(csv.DictReader(f))
rows = [types.SimpleNamespace(**row['record']) for row in current['rows']]
by_id = {r.id: r for r in rows}
approved = {int(d['master_id']) for d in decisions if d['adjudication_decision'] == 'APPROVED_FOR_GEOGRAPHIC_CORRECTION'}
all_decision_ids = {int(d['master_id']) for d in decisions}
expected_before = set(map(int, api['unique_master_ids']))

class ScalarResult:
    def __init__(self, values): self.values = values
    def all(self): return self.values
class FakeDB:
    def __init__(self, values): self.values = values
    def scalars(self, statement): return ScalarResult(self.values)

def payload(values):
    return main._national_map_payload(FakeDB(values), [], {'dataset_version': 'read-only-in-memory-302-evidence-simulation'})
def ids_from_payload(p): return {int(i) for point in p['points'] for i in point['ids']}

checks = {}
checks['snapshot_rows_518'] = len(rows) == 518 and len(by_id) == 518
checks['single_governorate_snapshot'] = all(str(x.get('governorate_external_id')) == '501' and str(x.get('region_external_id')) == '5' for x in current['rows'])
checks['decision_register_exactly_302_unique'] = len(decisions) == 302 and len(all_decision_ids) == 302
checks['approved_subset_exactly_302'] = len(approved) == 302 and approved == all_decision_ids and approved <= set(by_id)
before_fields = {i: (by_id[i].geographic_scope, by_id[i].latitude, by_id[i].longitude, json.dumps(by_id[i].coordinate_provenance_json, sort_keys=True), by_id[i].canonical_id, by_id[i].merged_into_id) for i in by_id}
before = payload(rows)
before_ids = ids_from_payload(before)
checks['baseline_total_518'] = before['counts']['total'] == 518
checks['baseline_payload_145'] = before['counts']['exact_mapped'] == 145 and len(before_ids) == 145
checks['baseline_matches_live_api_ids'] = before_ids == expected_before

# In-memory copies only. No ORM session or database is connected.
simulated = [types.SimpleNamespace(**vars(row)) for row in rows]
sim_by_id = {r.id: r for r in simulated}
for i in approved:
    sim_by_id[i].geographic_scope = 'SPECIFIC_LOCATION'
after = payload(simulated)
after_ids = ids_from_payload(after)
checks['simulated_total_518'] = after['counts']['total'] == 518
checks['approved_all_present'] = approved <= after_ids
checks['prior_145_preserved'] = expected_before <= after_ids
checks['only_approved_added'] = after_ids - before_ids == approved
checks['simulated_eligible_447'] = after['counts']['exact_mapped'] == 447 and len(after_ids) == 447
checks['held_master_64_excluded'] = 64 not in after_ids
checks['coordinates_and_identity_unchanged'] = all((sim_by_id[i].latitude, sim_by_id[i].longitude, json.dumps(sim_by_id[i].coordinate_provenance_json, sort_keys=True), sim_by_id[i].canonical_id, sim_by_id[i].merged_into_id) == (before_fields[i][1], before_fields[i][2], before_fields[i][3], before_fields[i][4], before_fields[i][5]) for i in by_id)
checks['only_scope_changed_for_approved'] = all((sim_by_id[i].geographic_scope == 'SPECIFIC_LOCATION') if i in approved else (sim_by_id[i].geographic_scope == before_fields[i][0]) for i in by_id)
checks['max_coordinate_rounding_delta_le_1e_7'] = max((abs(float(point['latitude'])-float(sim_by_id[i].latitude)) for point in after['points'] for i in point['ids']), default=0) <= 1e-7 and max((abs(float(point['longitude'])-float(sim_by_id[i].longitude)) for point in after['points'] for i in point['ids']), default=0) <= 1e-7

result = {
 'mode':'NON_MUTATING_IN_MEMORY_ACTUAL_LIVE_API_PAYLOAD_BUILDER',
 'network':'none (ephemeral container)',
 'database':'none (fake DB result; no SQL connection)',
 'image':'sha256:1536c3e3229684fd2feee62aa3bf896c2b3d35d1bf585522abed3d7d6d62a59a',
 'api_module_function':'app.main._national_map_payload',
 'approved_master_ids':sorted(approved),
 'approved_count':len(approved),
 'baseline':{'counts':before['counts'],'unique_master_ids':sorted(before_ids),'unique_point_count':len(before['points'])},
 'simulation':{'counts':after['counts'],'unique_master_ids':sorted(after_ids),'unique_point_count':len(after['points']),'added_ids':sorted(after_ids-before_ids),'new_point_count_delta':len(after['points'])-len(before['points'])},
 'checks':checks,
 'passed':all(checks.values()),
 'production_data_mutations':0,
 'production_service_changes':0,
 'created_at_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
}
output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'passed':result['passed'],'checks':checks,'baseline':before['counts'],'simulated':after['counts'],'added_count':len(after_ids-before_ids),'new_point_count_delta':len(after['points'])-len(before['points'])}, ensure_ascii=False, indent=2))
sys.exit(0 if result['passed'] else 2)