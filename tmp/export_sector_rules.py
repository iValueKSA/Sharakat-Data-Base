import json
from app.sector_classification import ENGINE_VERSION,TEXT_RULES,ACTIVITY_EXACT,SUBACTIVITY_EXACT,ASSET_EXACT,RELAXED_VERSION,STRUCTURED_RULES
from app.sector_inference import SECTOR_LABELS_BY_ID,GENERIC_OR_WRONG_DIMENSION
from app.sector_inference_relaxed import TITLE_RULES,ASSET_RULES,GENERIC_ONLY,TOURISM_NEGATIVES,AGRICULTURE_NEGATIVES,MEDIUM_MIN_CONFIDENCE,MEDIUM_MAX_CONFIDENCE
from app.sector_inference_phase2 import ENGINE_VERSION as PHASE2_VERSION,EXACT_SUBACTIVITY_RULES,ACTIVITY_MAP,SUBACTIVITY_MAP,STRUCTURED_SUBACTIVITY_SIGNALS,RAW_SOURCE_MAP,PHRASE_RULES,NEGATIVE_RULES
from app.standardization import canonical_id
obj={
 'classifier_version':ENGINE_VERSION,
 'base_engines':{'controlled_relaxation':RELAXED_VERSION,'phase2':PHASE2_VERSION},
 'canonical_taxonomy':{k:v for k,v in sorted(SECTOR_LABELS_BY_ID.items())},
 'weights_and_decisions':{
  'explicit_source_sector':100,'activity_exact':90,'sub_activity_exact':96,'source_activity_exact':90,'source_sub_activity_exact':96,
  'raw_activity_type':84,'raw_sub_activity_type':88,'primary_purpose_title':66,'primary_purpose_other_text':45,
  'generic_warehouse_context':27,'asset_exact':{k:{'sector_id':v[0],'weight':v[1],'rule_key':v[2]} for k,v in ASSET_EXACT.items()},
  'fallback_temporary_rental':{'commercial_peer_count':28,'other_alternative_peer_count':5,'commercial_weight':28,'other_weight':5},
  'fallback_generic_investment_context':{'sector_id':'sector:commercial','weight':10},
  'deduplicate_same_signal_across_fields':True,'low_confidence_label':'LOW','low_confidence_method':'FORCED_BEST_FIT',
  'authoritative_conflict_prevents_high_confidence':True,'high_confidence_margin_threshold':18,'medium_primary_purpose_min_score':60,'medium_margin_threshold':18,
  'accepted_medium_confidence_range':[MEDIUM_MIN_CONFIDENCE,MEDIUM_MAX_CONFIDENCE]
 },
 'governed_primary_purpose_text_rules':TEXT_RULES,
 'governed_exact_activity_mappings':ACTIVITY_EXACT,
 'governed_exact_sub_activity_mappings':SUBACTIVITY_EXACT,
 'accepted_phase2':{'exact_subactivity_pairs':{f'{a} | {b}':v for (a,b),v in EXACT_SUBACTIVITY_RULES.items()},'activity_map':ACTIVITY_MAP,'subactivity_map':SUBACTIVITY_MAP,'structured_subactivity_signals':STRUCTURED_SUBACTIVITY_SIGNALS,'raw_source_map':RAW_SOURCE_MAP,'phrase_rules':PHRASE_RULES,'negative_rules':NEGATIVE_RULES},
 'accepted_relaxed':{'title_rules':TITLE_RULES,'structured_rules':STRUCTURED_RULES,'asset_rules':ASSET_RULES,'generic_only_phrases':GENERIC_ONLY,'tourism_negatives':TOURISM_NEGATIVES,'agriculture_negatives':AGRICULTURE_NEGATIVES},
 'source_values_excluded_from_sector_dimension':sorted(GENERIC_OR_WRONG_DIMENSION),
 'fallback_policy':{'missing_evidence_to_other':False,'unresolved_current_master': 'single best-supported canonical sector with LOW/FORCED_BEST_FIT provenance'}
}
print(json.dumps(obj,ensure_ascii=False,indent=2,default=lambda x:list(x) if isinstance(x,tuple) else str(x)))
