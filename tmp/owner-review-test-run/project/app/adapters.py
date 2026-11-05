from __future__ import annotations
import hashlib, json, re, ssl
import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, parse_qs
import httpx
from bs4 import BeautifulSoup
from .normalization import classify_location, normalize_arabic, parse_number

PARSER_VERSION = "2026.10.11-3"
LOCATION_ACCEPTANCE_THRESHOLD=float(os.getenv("LOCATION_ACCEPTANCE_THRESHOLD","0.85"))

@dataclass
class RawOpportunity:
    external_id: str
    title: str
    url: str
    owner: str | None = None
    location: str | None = None
    area_text: str | None = None
    activity: str | None = None
    sub_activity: str | None = None
    contract_text: str | None = None
    deadline: str | None = None
    status: str | None = None
    reference: str | None = None
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    raw: dict | None = None
    location_source_filtered: bool = False

    @property
    def content_hash(self) -> str:
        body = json.dumps(self.__dict__, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(body.encode()).hexdigest()

class BaseSourceAdapter:
    key = ""
    url = ""
    headers = {"User-Agent": "AlAhsaOpportunityMonitor/1.0 (public research contact: public sources only)"}

    async def fetch(self, client: httpx.AsyncClient) -> tuple[list[RawOpportunity], int]:
        raise NotImplementedError

class SourceBlocked(RuntimeError):
    """A publisher explicitly denied public access; never treat it as an empty snapshot."""

class AhdaAdapter(BaseSourceAdapter):
    key="ahda"
    url="https://www.ahda.gov.sa/"
    sitemap_url="https://www.ahda.gov.sa/sitemap.xml"
    parser_version="2026.10.11-ahda-1"
    terms=("الفرص الاستثمارية","الاستثمار","الشراكات","المشاريع","المستثمر","القطاع الخاص","investment","partnership","strategic projects","major projects","private sector","investor")
    actionable=("فرصة استثمارية","فرص استثمارية","طلب شراكة","دعوة للمستثمرين","مشاركة القطاع الخاص","شريك استثماري","investment opportunity","investor participation","private sector participation","partnership opportunity","call for investors","apply now")
    non_actionable=("اجتماع المستثمرين","ملتقى الاستثمار","منتدى الاستثمار","مذكرة تفاهم","إحصاءات الاستثمار","investment forum","investment meeting","memorandum of understanding","investment statistics")

    def __init__(self): self.metrics={};self.content_items=[];self.diagnostics=[]

    async def fetch(self,client):
        from bs4 import BeautifulSoup
        headers={**self.headers,"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36","Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Accept-Language":"ar,en;q=0.8"}
        try:
            response=await client.get(self.sitemap_url,headers=headers)
            if response.status_code==403: raise SourceBlocked("AHDA sitemap returned HTTP 403")
            response.raise_for_status()
        except SourceBlocked: raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401,403,429): raise SourceBlocked(f"AHDA sitemap access blocked (HTTP {exc.response.status_code})") from exc
            raise
        soup=BeautifulSoup(response.text,"xml")
        all_urls=[node.get_text(strip=True) for node in soup.select("loc")]
        # Sitemap discovery confirmed these live AHDA content sections. News and events are
        # included for classification but are never qualified from their section label alone.
        targets=[u for u in all_urls if re.search(r"/(?:invest-al-ahsa/(?:investment-opportunities|major-projects|investment-sectors|business-enablers)|media-center/(?:news|announcements|events|press-releases))",u,re.I)]
        targets=list(dict.fromkeys(targets))
        semaphore=asyncio.Semaphore(4)
        async def parse_page(url):
            async with semaphore:
                for attempt in range(3):
                    try:
                        page=await client.get(url,headers={**headers,"Referer":self.url})
                        if page.status_code==403: raise SourceBlocked(f"AHDA page access blocked: {url}")
                        page.raise_for_status()
                        break
                    except SourceBlocked: raise
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code in (401,403,429): raise SourceBlocked(f"AHDA page access blocked (HTTP {exc.response.status_code}): {url}") from exc
                        if exc.response.status_code>=500 and attempt<2:
                            await asyncio.sleep(.5*(attempt+1));continue
                        return {"url":url,"error":f"HTTP {exc.response.status_code}"}
                    except httpx.HTTPError as exc:
                        if attempt<2:
                            await asyncio.sleep(.5*(attempt+1));continue
                        return {"url":url,"error":str(exc)}
                try:
                    doc=BeautifulSoup(page.text,"html.parser")
                    title_node=doc.select_one("h1") or doc.select_one("title")
                    title=title_node.get_text(" ",strip=True) if title_node else ""
                    main=doc.select_one("main") or doc.body or doc
                    raw_text=re.sub(r"\s+"," ",main.get_text(" ",strip=True))[:50000]
                    description=(doc.select_one('meta[name="description"]') or {}).get("content","")
                    pub=next((meta.get("content") for meta in doc.select('meta[property="article:published_time"],meta[name="date"],time[datetime]') if meta.get("content") or meta.get("datetime")),None)
                    attachments=[]
                    for a in main.select("a[href]"):
                        href=urljoin(url,a.get("href","")); name=a.get_text(" ",strip=True) or href.rsplit("/",1)[-1]
                        if re.search(r"\.(?:pdf|docx?|xlsx?)(?:\?|$)",href,re.I): attachments.append({"filename":name,"url":href,"type":href.split("?")[0].rsplit(".",1)[-1].lower()})
                    lower=(title+" "+raw_text).casefold()
                    keywords=[term for term in self.terms if term.casefold() in lower]
                    path=urlparse(url).path.lower()
                    if "/investment-opportunities/" in path: kind="INVESTMENT_OPPORTUNITY"
                    elif "/major-projects/" in path: kind="STRATEGIC_PROJECT"
                    elif any(k in lower for k in ("partnership opportunity","طلب شراكة","شراكة استثمارية")): kind="PARTNERSHIP_OPPORTUNITY"
                    elif "/investment-sectors/" in path: kind="INVESTMENT_SECTOR_INFORMATION"
                    elif "/business-enablers/" in path: kind="INVESTMENT_SECTOR_INFORMATION"
                    elif any(k in lower for k in ("investment announcement","إعلان استثماري")): kind="INVESTMENT_ANNOUNCEMENT"
                    elif any(k in path for k in ("/news/","/events/","/announcements/","/press-releases/")): kind="NON_INVESTMENT_CONTENT"
                    else: kind="GENERAL_PROJECT"
                    path_actionable=(kind=="INVESTMENT_OPPORTUNITY" and not path.startswith("/en/"))
                    action_evidence=any(term.casefold() in lower for term in self.actionable)
                    false_positive=any(term.casefold() in lower for term in self.non_actionable)
                    qualified=(path_actionable and bool(title) or kind in ("PARTNERSHIP_OPPORTUNITY","INVESTMENT_ANNOUNCEMENT") and action_evidence) and not (false_positive and not action_evidence)
                    payload={"url":url,"title":title,"publication_date":pub,"content_type":kind,"raw_text":raw_text,"extracted_description":description or raw_text[:2000],"attachments":attachments,"detected_keywords":keywords,"parser_version":self.parser_version,"qualified":qualified,"extraction_method":"sitemap+server-rendered HTML","fingerprint":hashlib.sha256((title+"\n"+raw_text+"\n"+json.dumps(attachments,sort_keys=True,ensure_ascii=False)).encode()).hexdigest()}
                    return payload
                except SourceBlocked: raise
        pages=await asyncio.gather(*(parse_page(url) for url in targets))
        # A single intermittent 5xx during a large publisher sweep should not leave the
        # source permanently incomplete. Retry only failed pages after the concurrent pass.
        failed=[item for item in pages if "error" in item]
        retry_pages_requested=0
        if failed:
            retry_pages_requested=len(failed)
            retry_results=await asyncio.gather(*(parse_page(item["url"]) for item in failed))
            replacements={item["url"]:item for item in retry_results}
            pages=[replacements.get(item["url"],item) if "error" in item else item for item in pages]
        self.content_items=[item for item in pages if "title" in item]
        errors=[item for item in pages if "error" in item]
        if targets and len(self.content_items)==0:
            self.diagnostics.append("Sitemap listed target pages, but no page parsed into a title/content item.")
        records=[]
        for item in self.content_items:
            if not item["qualified"]: continue
            # AHDA is the publisher/source of this page; the page content does not
            # identify the organization that owns each underlying opportunity.
            raw=RawOpportunity(external_id=item["url"],title=item["title"],url=item["url"],owner=None,location=None,description=item["extracted_description"],raw={**item,"source_scope":"SOURCE_SCOPE_AL_AHSA","location_detection_method":"SOURCE_SCOPE"},location_source_filtered=True)
            records.append(raw)
        parser_warning=any((not item.get("title") or len(item.get("raw_text", ""))<20) and re.search(r"/(?:investment-opportunities|major-projects)/[^/]+$",urlparse(item["url"]).path) for item in self.content_items)
        self.metrics={"source_total_reported":len(targets),"pages_requested":len(targets)+1+retry_pages_requested,"retry_pages_requested":retry_pages_requested,"pages_successful":len(self.content_items)-sum(1 for x in self.content_items if not x.get("title"))+1,"records_received":len(targets),"records_parsed":len(self.content_items),"unique_records":len(self.content_items),"qualified_opportunities":len(records),"rejected_content":len(self.content_items)-len(records),"pagination_complete":bool(targets) and not errors and not parser_warning and len(self.content_items)==len(targets),"parser_warning":parser_warning,"error_pages":len(errors),"page_errors":[{"url":x["url"],"error":x["error"]} for x in errors[:50]],"investment_pages":sum(1 for x in self.content_items if any(t.casefold() in (x["title"]+" "+x["raw_text"]).casefold() for t in self.terms)),"attachments":sum(len(x["attachments"]) for x in self.content_items)}
        self.diagnostics.append(f"AHDA sitemap listed {len(all_urls)} pages; scanned {len(self.content_items)}/{len(targets)} targeted pages.")
        return records,len(self.content_items)+1

class InvestSaudiAdapter(BaseSourceAdapter):
    key="invest-saudi"
    url="https://investsaudi.sa/investment-opportunities"
    api="https://investsaudi.sa/backend/wp-json/v3/opportunities"
    projects_api="https://investsaudi.sa/backend/wp-json/v3/investment-projects"
    pif_api="https://investsaudi.sa/backend/wp-json/v3/pif-opportunities"
    regional_api="https://investsaudi.sa/backend/wp-json/v3/regional-opportunities"
    parser_version="2026.10.12-investsaudi-2"
    page_size=100

    def __init__(self): self.metrics={};self.raw_records=[];self.location_reviews=[];self.raw_candidates=[]

    @staticmethod
    def filter_summary(meta):
        filters=meta.get("filters") or {};summary={}
        for key in ("sectors","regions","companies"):
            values=filters.get(key)
            if values is None:continue
            summary[key]=[{name:item.get(name) for name in ("slug","title","count") if item.get(name) is not None} if isinstance(item,dict) else str(item) for item in values]
        return summary

    async def fetch(self,client):
        headers={**self.headers,"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36","Accept":"application/json,text/plain,*/*","Referer":self.url}
        async def collect_endpoint(endpoint,explicit_total_pages=False):
            async def get_page(page):
                response=await client.get(endpoint,params={"page":page,"per_page":self.page_size},headers=headers)
                if response.status_code in (401,403,429): raise SourceBlocked(f"Invest Saudi public API access blocked (HTTP {response.status_code})")
                response.raise_for_status();return response.json()
            first=await get_page(1);meta=first.get("meta") or {};total=meta.get("total")
            if total is None: raise RuntimeError(f"Invest Saudi API {endpoint} did not report a total; completeness cannot be established")
            page_size=int(meta.get("per_page") or self.page_size)
            if page_size<1 or page_size>self.page_size: raise RuntimeError("Invest Saudi API returned an unexpected page size")
            pages=meta.get("totalPages",meta.get("total_pages"))
            pages=int(pages) if pages is not None else (int(total)+page_size-1)//page_size
            if int(total)==0:pages=1
            payloads=[first]
            for page_no in range(2,pages+1):payloads.append(await get_page(page_no))
            rows=[];seen=set()
            for payload in payloads:
                for item in payload.get("data",[]):
                    identifier=str(item.get("id") or item.get("slug") or item.get("link") or "").strip()
                    if not identifier or identifier in seen:continue
                    seen.add(identifier);rows.append(item)
            complete=(len(payloads)==pages and len(rows)==int(total) and all(len((p.get("data") or []))<=page_size for p in payloads))
            return {"endpoint":endpoint,"meta":meta,"total":int(total),"pages":pages,"page_size":page_size,"payloads":payloads,"rows":rows,"complete":complete}
        opportunity_collection=await collect_endpoint(self.api,explicit_total_pages=True)
        project_collection=await collect_endpoint(self.projects_api)
        pif_collection=await collect_endpoint(self.pif_api,explicit_total_pages=True)
        regional_collection=await collect_endpoint(self.regional_api,explicit_total_pages=True)
        collections=(opportunity_collection,project_collection,pif_collection,regional_collection)
        total=sum(c["total"] for c in collections);pages=sum(c["pages"] for c in collections)
        rows=[]
        for collection in collections:
            family={id(opportunity_collection):"opportunity",id(project_collection):"project",id(pif_collection):"pif",id(regional_collection):"regional"}[id(collection)]
            for item in collection["rows"]:rows.append((family,collection,item))
        candidates_by_official_id={}
        for family,collection,item in rows:
            modal=item.get("modalData") or {};geo=modal.get("location") or {}
            title=str(item.get("title") or "").strip();description=str(item.get("description") or "").strip()
            if family=="project":
                description=" ".join(x for x in (description,*(str(x.get("content") or "") for x in modal.get("descriptionSections",[]))) if x).strip()
                location=" ".join(x for x in (str(item.get("location") or "").strip(),str(geo.get("street") or "").strip(),str(geo.get("neighborhood") or "").strip(),str(geo.get("siteDescription") or "").strip()) if x)
                region=str(item.get("region") or "").strip();sector=str(item.get("category") or "").strip() or None
                source_subsector=item.get("activity") or item.get("subActivity")
                reference=str(modal.get("opportunityNumber") or "").strip() or None
                # The Invest Saudi record's municipality is context, not a proven
                # opportunity owner. Preserve it in the raw record for review.
                owner=None
                url=self.url
            elif family=="opportunity":
                location=str(item.get("location") or "").strip();region=str(item.get("region") or "").strip();sector=str(item.get("sector_name") or "").strip() or None
                source_subsector=None;reference=str(item.get("id") or "");owner=None
                url=str(item.get("link") or f"https://investsaudi.sa/opportunities/{item.get('slug','')}")
            elif family=="pif":
                location=str(item.get("location") or "").strip();region=str(item.get("region") or "").strip()
                sector=_taxonomy_label(item.get("sector"))
                source_subsector=None;reference=str(item.get("id") or "") or None
                # Portfolio company is a related entity, not owner evidence.
                owner=None;url=self.url
                details=item.get("details") or item.get("description") or ""
                description=" ".join(str(x) for x in _flatten_text(details) if str(x).strip())
            else:
                location=str(item.get("location") or item.get("city") or "").strip();region=str(item.get("region") or "").strip()
                sector=_taxonomy_label(item.get("sector") or item.get("category"));source_subsector=None
                reference=str(item.get("id") or "") or None
                # Portfolio company is a related entity, not owner evidence.
                owner=None;url=self.url
                description=str(item.get("description") or "").strip()
            coordinates=item.get("Coordinates") or item.get("coordinates") or {}
            if isinstance(coordinates,str):
                parts=re.split(r"[,;\s]+",coordinates.strip())
                coordinates={"latitude":parts[0],"longitude":parts[1]} if len(parts)>=2 else {}
            if family=="project": coordinates={"latitude":geo.get("latitude"),"longitude":geo.get("longitude")}
            location_item={**item,"coordinates":coordinates}
            latitude=coordinates.get("latitude") if isinstance(coordinates,dict) else None
            longitude=coordinates.get("longitude") if isinstance(coordinates,dict) else None
            confidence,method,evidence,city=investsaudi_location(location_item, location, region, title, description)
            normalized_sector=normalize_sector(sector)
            original_id=str(item.get("id") or item.get("slug") or item.get("link") or "").strip()
            normalized_id=str(int(original_id)) if original_id.isdigit() else original_id.casefold()
            if not normalized_id:raise RuntimeError(f"Invest Saudi {family} record has no stable source identifier")
            external_id=f"investsaudi:{normalized_id}"
            dataset_name={"opportunity":"Opportunities","project":"Investment projects","pif":"PIF opportunities","regional":"Regional opportunities"}[family]
            item_raw={**item,"official_source_id_original":original_id,"official_source_id_normalized":normalized_id,"source_record_family":family,"dataset_name":dataset_name,"source_taxonomy":{"sector":sector,"subsector":source_subsector},"normalized_taxonomy":{"sector":normalized_sector,"subsector":None},"taxonomy_mapping_version":"1","location_confidence_score":confidence,"location_detection_method":method,"location_evidence":evidence,"source_api":collection["endpoint"],"source_endpoint_method":"GET","source_endpoint_pagination":{"page_size":collection["page_size"],"total_pages":collection["pages"],"total":collection["total"]},"parser_version":self.parser_version}
            self.raw_records.append(item_raw)
            observation={"dataset_name":dataset_name,"endpoint":collection["endpoint"],"official_source_id_original":original_id,"official_source_id_normalized":normalized_id,"source_taxonomy":item_raw["source_taxonomy"],"normalized_taxonomy":item_raw["normalized_taxonomy"],"location_confidence_score":confidence,"location_detection_method":method,"location_evidence":evidence,"raw_data_json":item}
            candidate=RawOpportunity(external_id=external_id,title=title,url=url,owner=owner,location=" | ".join(x for x in (location,region) if x) or None,activity=(str(item.get("activity")).strip() if family=="project" and item.get("activity") not in (None,"") else None),sub_activity=(str(item.get("subActivity")).strip() if family=="project" and item.get("subActivity") not in (None,"") else None),description=description,reference=reference,area_text=str(geo.get("siteArea") or "") or None,contract_text=str(modal.get("contractPeriod") or "") or None,latitude=latitude,longitude=longitude,raw={**item_raw,"publication_date":item.get("date") or item.get("published_at"),"qualified_location":confidence>=LOCATION_ACCEPTANCE_THRESHOLD,"source_observations":[observation],"dataset_memberships":[{"dataset_name":dataset_name,"endpoint":collection["endpoint"],"dataset_specific_metadata":{"source_taxonomy":item_raw["source_taxonomy"],"normalized_taxonomy":item_raw["normalized_taxonomy"]}}]},location_source_filtered=confidence>=LOCATION_ACCEPTANCE_THRESHOLD)
            candidates_by_official_id.setdefault(normalized_id,[]).append(candidate)
        accepted=[];location_reviews=[];all_source_records=[]
        for normalized_id,representations in candidates_by_official_id.items():
            priority={"opportunity":0,"project":1,"pif":2,"regional":3}
            primary=min(representations,key=lambda r:priority.get((r.raw or {}).get("source_record_family"),99))
            best_location=max(representations,key=lambda r:float((r.raw or {}).get("location_confidence_score",0)))
            observations=[obs for representation in representations for obs in (representation.raw or {}).get("source_observations",[])]
            memberships=[];membership_keys=set();taxonomies=[];taxonomy_keys=set()
            for obs in observations:
                membership_key=(obs["dataset_name"],obs["endpoint"])
                if membership_key not in membership_keys:
                    membership_keys.add(membership_key);memberships.append({"dataset_name":obs["dataset_name"],"endpoint":obs["endpoint"],"dataset_specific_metadata":{"source_taxonomy":obs["source_taxonomy"],"normalized_taxonomy":obs["normalized_taxonomy"]}})
                tax=(obs["dataset_name"],obs["source_taxonomy"].get("sector"),obs["source_taxonomy"].get("subsector"))
                if tax not in taxonomy_keys:
                    taxonomy_keys.add(tax);taxonomies.append({"dataset_name":tax[0],"source_taxonomy_value":tax[1],"source_subsector":tax[2],"normalized_taxonomy_value":obs["normalized_taxonomy"].get("sector")})
            merged_raw={**(primary.raw or {}),"official_source_id_original":str(primary.raw.get("official_source_id_original")),"official_source_id_normalized":normalized_id,"source_observations":observations,"dataset_memberships":memberships,"source_taxonomies":taxonomies,"location_confidence_score":best_location.raw.get("location_confidence_score",0),"location_detection_method":best_location.raw.get("location_detection_method",""),"location_evidence":best_location.raw.get("location_evidence",""),"location_evidence_by_dataset":[{"dataset_name":o["dataset_name"],"score":o["location_confidence_score"],"method":o["location_detection_method"],"evidence":o["location_evidence"]} for o in observations],"qualified_location":float(best_location.raw.get("location_confidence_score",0))>=LOCATION_ACCEPTANCE_THRESHOLD}
            location=next((r.location for r in representations if r.location),primary.location)
            latitude=next((r.latitude for r in representations if r.latitude is not None),None);longitude=next((r.longitude for r in representations if r.longitude is not None),None)
            reference=next((r.reference for r in representations if r.reference),primary.reference)
            description=max((r.description or "" for r in representations),key=len,default=primary.description)
            candidate=RawOpportunity(external_id=f"investsaudi:{normalized_id}",title=primary.title,url=primary.url,owner=primary.owner,location=location,area_text=primary.area_text,activity=primary.activity,sub_activity=primary.sub_activity,contract_text=primary.contract_text,deadline=primary.deadline,status=primary.status,reference=reference,description=description,latitude=latitude,longitude=longitude,raw=merged_raw,location_source_filtered=merged_raw["qualified_location"])
            all_source_records.append(candidate)
            score=float(merged_raw["location_confidence_score"])
            if score>=LOCATION_ACCEPTANCE_THRESHOLD:
                accepted.append(candidate)
            elif score>=max(.75,LOCATION_ACCEPTANCE_THRESHOLD-.10):
                location_reviews.append({"external_id":candidate.external_id,"title":candidate.title,"sector":primary.raw.get("source_taxonomy",{}).get("sector"),"location":location,"description":description,"latitude":latitude,"longitude":longitude,"evidence":merged_raw["location_evidence"],"confidence_score":score,"reason":"Explicit Al-Ahsa evidence appears in descriptive text; verify that the asset itself is located in Al-Ahsa."})
        self.location_reviews=location_reviews
        self.raw_candidates=all_source_records
        endpoint_rows=sum(sum(len(p.get("data",[])) for p in c["payloads"]) for c in collections)
        duplicate_endpoint_memberships=endpoint_rows-len(all_source_records)
        self.metrics={"source_total_reported":total,"opportunities_total":opportunity_collection["total"],"investment_projects_total":project_collection["total"],"pif_opportunities_total":pif_collection["total"],"regional_opportunities_total":regional_collection["total"],"pages_requested":pages,"pages_successful":sum(len(c["payloads"]) for c in collections),"records_received":endpoint_rows,"endpoint_rows_received":endpoint_rows,"records_parsed":len(rows),"unique_records":len(all_source_records),"unique_official_ids":len(all_source_records),"duplicate_endpoint_memberships":duplicate_endpoint_memberships,"dataset_memberships":sum(len(r.raw.get("dataset_memberships",[])) for r in all_source_records),"source_opportunities_created":None,"source_opportunities_updated":None,"explicit_ahsa_matches":sum(1 for x in all_source_records if (x.raw or {}).get("location_detection_method") in ("EXPLICIT_LOCALITY_FIELD","CONFIRMED_CITY_FIELD")),"accepted_records":len(accepted),"active_count":len(accepted),"location_review_count":len(location_reviews),"rejected_records":len(all_source_records)-len(accepted)-len(location_reviews),"pagination_complete":all(c["complete"] for c in collections),"page_size":self.page_size,"endpoints":[{"endpoint":c["endpoint"],"method":"GET","page_size":c["page_size"],"pages":c["pages"],"total":c["total"],"filters":self.filter_summary(c["meta"])} for c in collections],"available_filters":self.filter_summary(opportunity_collection["meta"]),"region_field":"region","city_field":"location","coordinates_available":any(x.latitude is not None and x.longitude is not None for x in all_source_records)}
        return accepted,sum(len(c["payloads"]) for c in collections)

def investsaudi_location(item,location,region,title,description):
    location_norm=normalize_arabic(location);region_norm=normalize_arabic(region)
    ahsa_tokens=("الاحساء","الاحسا","al ahsa","al-ahsa","alahsa","al hasa","al-hasa")
    city_tokens=("الهفوف","المبرز","hofuf","al hofuf","al-hofuf")
    direct=" ".join((location,region))
    direct_norm=normalize_arabic(direct)
    if any(normalize_arabic(t) in direct_norm for t in ahsa_tokens):return 1.0,"EXPLICIT_LOCALITY_FIELD",direct,"الأحساء"
    if any(normalize_arabic(t) in direct_norm for t in city_tokens):return .95,"CONFIRMED_CITY_FIELD",direct,"الهفوف" if "hofuf" in direct_norm or "الهفوف" in direct_norm else "المبرز"
    coords=item.get("coordinates") or item.get("location_coordinates") or {}
    lat=item.get("latitude",coords.get("latitude") if isinstance(coords,dict) else None);lon=item.get("longitude",coords.get("longitude") if isinstance(coords,dict) else None)
    try:
        lat=float(lat);lon=float(lon)
        # Conservative Al-Ahsa oasis envelope, only used as location evidence, no city is inferred.
        if 25.0<=lat<=26.2 and 49.0<=lon<=50.1:return .90,"COORDINATES_AL_AHSA_ENVELOPE",f"coordinates:{lat},{lon}","الأحساء"
    except (TypeError,ValueError): pass
    if "eastern province" in region_norm or "المنطقه الشرقيه" in region_norm or "sharqia" in region_norm or "الشرقيه" in region_norm:
        if any(normalize_arabic(t) in normalize_arabic(description) for t in ahsa_tokens+city_tokens):return .80,"DESCRIPTION_ONLY_EXPLICIT_AL_AHSA",description,"الأحساء"
        return .30,"EASTERN_PROVINCE_ONLY",region,""
    if any(normalize_arabic(t) in location_norm for t in city_tokens):return .95,"CONFIRMED_CITY_FIELD",location,"الهفوف"
    if any(normalize_arabic(t) in normalize_arabic(description) for t in ahsa_tokens+city_tokens):return .80,"DESCRIPTION_ONLY_EXPLICIT_AL_AHSA",description,"الأحساء"
    return 0.0,"NO_AL_AHSA_EVIDENCE","No explicit Al-Ahsa location evidence in source location fields or description.",""

def _flatten_text(value):
    """Flatten the public PIF details payload without losing its text nodes."""
    if isinstance(value,dict):
        for child in value.values():
            yield from _flatten_text(child)
    elif isinstance(value,(list,tuple)):
        for child in value:
            yield from _flatten_text(child)
    elif value is not None and not isinstance(value,(bool,int,float)):
        yield str(value)

def _taxonomy_label(value):
    if isinstance(value,dict):
        for key in ("name","title","label","value"):
            if value.get(key):return str(value[key])
        return None
    return str(value).strip() if value not in (None,"") else None

def normalize_sector(value):
    """Map only reviewed complete source-sector labels; never guess by substring."""
    if value is None or not str(value).strip():
        return None
    from .standardization import canonical_identity
    identity=canonical_identity("sector",value)
    if identity and identity["id"] != "sector:unspecified":
        return identity["label"]
    key=normalize_arabic(value).strip().casefold()
    approved={
        "real estate and construction":"العقارات والإنشاءات", "real estate & construction":"العقارات والإنشاءات", "real estate":"العقارات والإنشاءات",
        "العقارات":"العقارات والإنشاءات", "tourism":"السياحة", "السياحة":"السياحة",
        "agriculture and food processing":"الزراعة", "agriculture":"الزراعة", "الزراعة":"الزراعة",
        "transport and logistics":"الخدمات اللوجستية", "logistics":"الخدمات اللوجستية",
        "المياه":"البيئة", "water":"البيئة", "energy":"الطاقة", "الطاقة":"الطاقة",
        "education":"التعليم", "التعليم":"التعليم", "healthcare and medical devices":"الرعاية الصحية",
        "healthcare medical devices":"الرعاية الصحية", "healthcare":"الرعاية الصحية", "الرعاية الصحية":"الرعاية الصحية",
        "machinery and equipment":"صناعي", "manufacturing":"صناعي", "industrial":"صناعي", "التصنيع":"صناعي",
        "recycling":"البيئة", "environment":"البيئة", "البيئة":"البيئة", "culture":"الثقافة", "media":"الثقافة",
        "sports":"الرياضة", "financial services":"الخدمات المالية", "biotechnology and pharma":"الرعاية الصحية",
        "biotechnology pharma":"الرعاية الصحية", "information and communication technology":"التقنية والاتصالات",
        "pv factory":"الطاقة", "defense and space":"التقنية والاتصالات", "mining and metals":"صناعي",
        "petrochemical and convention industries":"صناعي", "commercial":"تجاري", "تجاري":"تجاري",
        "other":"أخرى", "others":"أخرى", "أخرى":"أخرى", "بقية القطاعات":"أخرى",
    }
    return approved.get(key)

class AlAhsaOpportunitiesAdapter(BaseSourceAdapter):
    key = "alahsa-opportunities"
    url = "https://alahsa-opportunities.com/"

    def __init__(self): self.metrics={}

    async def fetch(self, client):
        import asyncio
        from urllib.parse import urljoin, urlparse, parse_qs
        async def request(url):
            last_error=None
            for attempt in range(3):
                try:
                    response=await client.get(url,headers=self.headers);response.raise_for_status();return response
                except httpx.HTTPError as exc:
                    last_error=exc
                    if attempt<2: await asyncio.sleep(1.5**attempt)
            raise RuntimeError(f"Al-Ahsa source request failed after retries: {last_error}")

        first=await request(self.url);first_soup=BeautifulSoup(first.text,"html.parser")
        max_page=1
        for link in first_soup.select('a[href*="page="]'):
            query=parse_qs(urlparse(urljoin(self.url,link.get("href",""))).query)
            try: max_page=max(max_page,int(query.get("page",["1"])[0]))
            except (TypeError,ValueError): pass
        # Header counts are split into the ordinary and featured categories.
        category_counts={}
        for link in first_soup.select('a[href*="category_id="]'):
            query=parse_qs(urlparse(urljoin(self.url,link.get("href",""))).query)
            category_id=query.get("category_id",[None])[0]
            match=re.search(r"([0-9٠-٩]+)\s*$",link.get_text(" ",strip=True))
            if category_id and match:
                category_counts[category_id]=parse_number(match.group(1))
        reported_total=sum(int(value) for value in category_counts.values()) if category_counts else None
        page_payloads=[(1,first,first_soup)]
        for page in range(2,max_page+1):
            response=await request(f"{self.url}?page={page}")
            page_payloads.append((page,response,BeautifulSoup(response.text,"html.parser")))

        result=[]; seen=set(); cards_received=0; parsed_count=0; repeated_ids=0; pages_successful=0
        active_count=0; expired_count=0; last_page_card_count=0; page_size=max(1,len(first_soup.select(".opportunity-card-row")))
        for page,response,soup in page_payloads:
            pages_successful+=1
            cards=soup.select(".opportunity-card-row");cards_received+=len(cards);last_page_card_count=len(cards)
            for card in cards:
                title_node = card.select_one(".card-title")
                link = card.select_one('a[href*="/opportunities/"]')
                if not title_node or not link:
                    continue
                title = title_node.get_text(" ", strip=True)
                url = urljoin(self.url, link.get("href", ""))
                identifier = re.search(r"/opportunities/(\d+)", url)
                record_id=identifier.group(1) if identifier else url
                parsed_count+=1
                if record_id in seen: repeated_ids+=1;continue
                seen.add(record_id)
                details = {}
                for item in card.select(".detail-item"):
                    label = item.select_one(".detail-label")
                    value = item.select_one(".detail-value")
                    if label and value:
                        details[label.get_text(" ", strip=True).rstrip(":")]=value.get_text(" ", strip=True)
                status_node=card.select_one(".status-badge")
                status=status_node.get_text(" ",strip=True) if status_node else None
                if status=="متاحة": active_count+=1
                elif status=="منتهية": expired_count+=1
                activity_value=details.get("نوع النشاط")
                result.append(RawOpportunity(
                external_id=record_id,
                title=title,
                url=url,
                # A portal affiliation and locally scoped listing do not establish
                # the owner of each opportunity. Keep owner unspecified unless a
                # source record supplies explicit owner evidence.
                owner=None,
                location=details.get("الموقع"),
                area_text=details.get("المساحة"),
                activity=activity_value,
                contract_text=details.get("مدة العقد"),
                deadline=details.get("آخر موعد"),
                status=status,
                description=title,
                raw={"details":details,"source":"server_rendered_html","page":str(response.url),"category_counts":category_counts,
                     "source_taxonomy":{"sector":activity_value},"normalized_taxonomy":{"sector":normalize_sector(activity_value)}},
                location_source_filtered=True,
                ))
        pagination_complete=(pages_successful==max_page and bool(page_payloads) and last_page_card_count<page_size)
        self.metrics={"source_total_reported":reported_total,"category_totals":category_counts,"pages_requested":max_page,
            "pages_successful":pages_successful,"records_received":cards_received,"records_parsed":parsed_count,
            "unique_records":len(result),"duplicate_items_between_pages":repeated_ids,"pagination_complete":pagination_complete,
            "active_count":active_count,"expired_count":expired_count,"page_size":page_size}
        return result,pages_successful

class FurasAdapter(BaseSourceAdapter):
    key = "furas"
    url = "https://furas.momah.gov.sa/ar/list-opportunities"
    config_url = "https://gisapps.balady.gov.sa/opportunities/assets/config.json"
    proxy_url = "https://gisapps.balady.gov.sa/opportunities/proxy/proxy.ashx?"
    # CITY_ID values confirmed in the live Furas layer for Al-Ahsa and its governorate localities.
    ahsa_city_ids = ("1949", "1945", "1950", "005011001", "9", "1264", "1315", "1299", "1298", "104", "005020001")

    def __init__(self): self.diagnostics=[];self.metrics={}

    async def fetch(self, client):
        async def request(url: str):
            last_error=None
            for attempt in range(3):
                try:
                    response=await client.get(url,headers=self.headers)
                    response.raise_for_status()
                    return response.json()
                except (httpx.HTTPError,ValueError) as exc:
                    last_error=exc
                    if attempt<2:
                        import asyncio
                        await asyncio.sleep(1.5**attempt)
            raise RuntimeError(f"Furas public map request failed after retries: {last_error}")

        config=await request(self.config_url)
        layer=(config["gisLayerUrl"]["investmentMapServerInvestmentP"]+"/"+
               str(config["gisLayerIndex"]["investmentMapServerInvestmentP"]))
        from datetime import date
        where=("CITY_ID IN ("+",".join("'"+city_id+"'" for city_id in self.ahsa_city_ids)+
               ") AND LASTRFPSELLDATE >= DATE '"+date.today().isoformat()+
               "' AND OPPORTUNITYACTIVESTATUS='Announced' AND QualifyingOpportunity=0")
        query_params={"f":"json","where":where,"returnIdsOnly":"true"}
        ids_payload=await request(self.proxy_url+layer+"/query?"+str(httpx.QueryParams(query_params)))
        if ids_payload.get("error"):
            raise RuntimeError(f"Furas ArcGIS ID query error: {ids_payload['error']}")
        ids=ids_payload.get("objectIds") or []
        if not ids:
            self.diagnostics.append("The official ArcGIS city filter returned zero feature IDs.")
            return [],1
        result=[]; calls=1;features_received=0;seen=set()
        for offset in range(0,len(ids),100):
            batch=ids[offset:offset+100]
            params={"f":"json","where":"OBJECTID IN ("+",".join(map(str,batch))+")","outFields":"*","returnGeometry":"true","orderByFields":"OBJECTID"}
            payload=await request(self.proxy_url+layer+"/query?"+str(httpx.QueryParams(params))); calls+=1
            if payload.get("error"):
                raise RuntimeError(f"Furas ArcGIS feature query error: {payload['error']}")
            for feature in payload.get("features",[]):
                features_received+=1
                attrs=feature.get("attributes") or {}
                reference=str(attrs.get("OPPORTUNITYID") or "").strip()
                object_id=str(attrs.get("OBJECTID") or "").strip()
                external_id=reference or object_id
                if not external_id or external_id in seen: continue
                seen.add(external_id)
                title=str(attrs.get("OPPORTUNITYDESCRIPTION") or reference or object_id).strip()
                city=str(attrs.get("CITYNAME") or "").strip()
                district=str(attrs.get("DISTRICT") or "").strip()
                street=str(attrs.get("STREET") or "").strip()
                # AMANA is the local municipality shown by the Furas map for these listings;
                # ENTITIESNAME is retained raw as the participating/publishing entity.
                owner=str(attrs.get("AMANA") or attrs.get("ENTITIESNAME") or "").strip() or None
                location=" ".join(piece for piece in (city,district,street) if piece)
                geometry=feature.get("geometry") or {}
                latitude=geometry.get("y"); longitude=geometry.get("x")
                if str(attrs.get("OPPORTUNITYTYPE") or "") in ("TempRental","TemporaryRental"):
                    duration=None
                else:
                    months=parse_number(str(attrs.get("DURATION") or ""))
                    duration=f"{months/12:g} سنة" if months is not None else None
                deadline=epoch_date(attrs.get("LASTRFPSELLDATE") or attrs.get("ENDDATE"))
                published=epoch_date(attrs.get("STARTDATE") or attrs.get("CREATED_DATE"))
                activity_type=str(attrs.get("ACTIVITYTYPE") or "").strip().strip('"') or None
                if normalize_arabic(activity_type or "").strip().casefold() in {"الساحات الميادين","العربات المتنقلة","المباني"}:
                    activity_type=None  # Furas treats these as asset/format categories, not activities.
                result.append(RawOpportunity(
                    external_id=external_id,title=title,url=f"https://furas.momah.gov.sa/ar/opportunity/{reference}?type={attrs.get('OPPORTUNITYTYPE') or 'Investment'}" if reference else self.url,
                    owner=owner,location=location,area_text=str(attrs.get("TOTALSPACEINMETERS") or "") or None,
                    activity=activity_type,
                    sub_activity=str(attrs.get("SUBACTIVITYTYPE") or "").strip() or None,
                    contract_text=duration,deadline=deadline,status=str(attrs.get("OPPORTUNITYACTIVESTATUS") or attrs.get("STATUS") or "") or None,
                    reference=reference,description=title,latitude=latitude,longitude=longitude,
                    raw={"attributes":attrs,"geometry":geometry,"publication_date":published,"source_endpoint":layer,
                         "city_filter_ids":list(self.ahsa_city_ids),"source_filter_where":where},location_source_filtered=True,
                ))
        self.diagnostics.append(f"ArcGIS query: {len(ids)} source features across {calls} request(s); {len(result)} had confirmed Al-Ahsa evidence.")
        self.metrics={"source_total_reported":len(ids),"pages_requested":calls,"pages_successful":calls,
            "records_received":features_received,"records_parsed":features_received,"unique_records":len(result),
            "pagination_complete":len(result)==len(ids),"active_count":len(result),"expired_count":0,
            "page_size":100,"city_filter_ids":list(self.ahsa_city_ids),"where":where}
        return result,calls

def epoch_date(value):
    if value in (None,""): return None
    try:
        from datetime import datetime,timezone
        return datetime.fromtimestamp(float(value)/1000,tz=timezone.utc).date().isoformat()
    except (ValueError,TypeError,OSError): return str(value)

class KfuAdapter(BaseSourceAdapter):
    """King Faisal University investment announcements, separate from procurement notices."""
    key="kfu"
    url="https://www.kfu.edu.sa/ar/Departments/Investment/Documents/Newdesign/اعلانات-الإدارة.html"
    parser_version="2026.10.12-kfu-1"
    procurement_terms=("توريد","منافسة","مناقصة","procurement","supply tender")
    lease_terms=("تأجير","إيجار","lease","rent")
    operating_terms=("تشغيل","إدارة وتشغيل","operation","operate")
    commercial_terms=("مطاعم","متاجر","مجمع تجاري","مواقع تجارية","commercial complex","shops","restaurants")

    def __init__(self): self.metrics={};self.content_items=[];self.diagnostics=[]

    @classmethod
    def classify(cls,title,body):
        text=(title+" "+body).casefold()
        if any(k.casefold() in text for k in cls.procurement_terms) and not any(k.casefold() in text for k in cls.lease_terms+cls.operating_terms+cls.commercial_terms):
            return "PROCUREMENT_TENDER",False,"الطرح يطلب توريداً أو منافسة عامة ولا يثبت إتاحة أصل تجاري أو استثماري."
        if any(k.casefold() in text for k in cls.lease_terms):
            return "LEASE_OPPORTUNITY",True,"نص الإعلان يذكر تأجير موقع أو أصل جامعي للمستثمرين."
        if any(k.casefold() in text for k in cls.operating_terms):
            return "OPERATING_OPPORTUNITY",True,"نص الإعلان يطلب تشغيل أصل أو مرفق جامعي."
        if any(k.casefold() in text for k in cls.commercial_terms):
            return "COMMERCIAL_FACILITY_OPPORTUNITY",True,"الإعلان يحدد مواقع مطاعم ومتاجر ضمن مباني كليات الجامعة ويطرح تشغيلها بعقد ثلاث سنوات؛ لا تُستنتج ترسية من ذلك."
        return "GENERAL_ANNOUNCEMENT",False,"لا يثبت النص إتاحة أصل تجاري أو استثماري للقطاع الخاص."

    @staticmethod
    def deadline_status(deadline,today=None):
        today=today or datetime.now(timezone.utc).date().isoformat()
        return "EXPIRED" if deadline and deadline < today else "UNKNOWN"

    async def fetch(self,client):
        headers={**self.headers,"User-Agent":"Mozilla/5.0 (compatible; public opportunity monitor)","Accept-Language":"ar,en;q=0.8"}
        response=await client.get(self.url,headers=headers);response.raise_for_status()
        soup=BeautifulSoup(response.text,"html.parser")
        page_text=re.sub(r"\s+"," ",(soup.select_one("main") or soup.body or soup).get_text(" ",strip=True))
        links=[]
        for a in soup.select("a[href]"):
            href=urljoin(self.url,a.get("href",""));label=a.get_text(" ",strip=True) or href.rsplit("/",1)[-1]
            if re.search(r"\.(?:pdf|docx?|xlsx?)(?:\?|$)",href,re.I):
                links.append({"filename":label,"url":href,"type":href.split("?")[0].rsplit(".",1)[-1].lower(),"downloaded":False,"checksum":None})
        candidates=[]
        for panel in soup.select("li.AccordionPanel"):
            text=re.sub(r"\s+"," ",panel.get_text(" ",strip=True))
            if 25<=len(text)<=9000 and re.search(r"(?:\d{4}/\d{1,2}/\d{1,2}|كراسة|تأجير|مزايدة|فرصة استثمارية|منافسة)",text,re.I):candidates.append(text)
        if not candidates:
            text_nodes=soup.find_all(string=re.compile(r"(?:مزايدة|فرصة استثمارية|تأجير|مناقصة|طرح)",re.I))
            for node in text_nodes:
                current=node.parent
                for _ in range(6):
                    if not current or current.name in ("body","html"):break
                    text=re.sub(r"\s+"," ",current.get_text(" ",strip=True))
                    if "AccordionPanel" in (current.get("class") or []) and 25<=len(text)<=9000:
                        candidates.append(text);break
                    current=current.parent
        # The page may contain nested wrappers for one notice; deduplicate by title and
        # keep the largest matching text block so deadline and asset evidence survive.
        unique=[]
        for block in sorted(candidates,key=len,reverse=True):
            title=re.split(r"(?:موعد التقديم|موعد نهاية|قيمة الكراسة|مميزات الفرصة|الشروط|للاستفسار)",block,maxsplit=1)[0].strip(" •*-:،")[:350]
            if title and not any(normalize_arabic(title)==normalize_arabic(x[0]) for x in unique):unique.append((title,block))
        records=[]
        for index,(title,body) in enumerate(unique):
            kind,asset_evidence,reason=self.classify(title,body)
            deadline_match=re.search(r"(?:موعد نهاية تقديم العطاء|آخر موعد|آخر موعد للتقديم|deadline)[^0-9]{0,60}(\d{4}[/-]\d{1,2}[/-]\d{1,2})",body,re.I)
            deadline=deadline_match.group(1).replace("/","-") if deadline_match else None
            status=self.deadline_status(deadline)
            campus=bool(re.search(r"(?:جامعة الملك فيصل|كليات الجامعة|مباني الجامعة|حرم الجامعة)",body,re.I))
            qualified=asset_evidence and campus
            if asset_evidence and not campus: reason="الأصل التجاري محتمل لكن موقعه الجامعي غير محدد في الإعلان؛ يحتاج تحققاً جغرافياً."
            if not asset_evidence: reason += " لم يُنشأ سجل فرصة رئيسي لهذا المحتوى."
            external_id="kfu-announcement:"+hashlib.sha256((self.url+"\n"+normalize_arabic(title)).encode()).hexdigest()[:24]
            item={"url":self.url+"#"+external_id,"title":title,"publication_date":None,"content_type":kind,"raw_text":body,
                "extracted_description":body[:2500],"attachments":links,"detected_keywords":[],"parser_version":self.parser_version,
                "fingerprint":hashlib.sha256((body+json.dumps(links,ensure_ascii=False,sort_keys=True)).encode()).hexdigest(),"qualified":qualified,"qualification_reason":reason,
                "qualification_review_required":bool(not qualified and kind=="COMMERCIAL_FACILITY_OPPORTUNITY")}
            self.content_items.append(item)
            raw=RawOpportunity(external_id=external_id,title=title,url=item["url"],owner="جامعة الملك فيصل",location="جامعة الملك فيصل، الأحساء" if campus else None,
                deadline=deadline,status=status,description=body[:2500],raw={**item,"official_source_id":external_id,
                    "source_owner":"جامعة الملك فيصل","project_owner":"جامعة الملك فيصل","opportunity_type":kind,"qualification_reason":reason,
                    "qualification_review_required":bool(not qualified and kind=="COMMERCIAL_FACILITY_OPPORTUNITY"),
                    "deadline_evidence":"explicit announcement date" if deadline else None,"campus_scope_verified":campus,
                    "source_scope":"SOURCE_SCOPE_AL_AHSA" if qualified else None,"location_detection_method":"OFFICIAL_CAMPUS_SCOPE" if qualified else None,
                    "location_evidence":"Announcement names King Faisal University campus facilities in Al-Ahsa." if qualified else None,
                    "location_confidence_score":0.98 if qualified else 0.0},location_source_filtered=qualified)
            records.append(raw)
        if not self.content_items:
            # Keep the listing itself as a discovered content record; an empty parse is not
            # treated as an empty opportunity snapshot.
            self.content_items=[{"url":self.url,"title":soup.title.get_text(" ",strip=True) if soup.title else "KFU investment announcements",
                "content_type":"GENERAL_ANNOUNCEMENT","raw_text":page_text,"extracted_description":page_text[:2500],"attachments":links,
                "detected_keywords":[],"parser_version":self.parser_version,"fingerprint":hashlib.sha256(page_text.encode()).hexdigest()}]
        self.metrics={"source_total_reported":len(unique),"pages_requested":1,"pages_successful":1,"records_received":len(unique),
            "records_parsed":len(unique),"unique_records":len(unique),"qualified_opportunities":sum(bool(x.raw.get("qualified")) for x in records),
            "rejected_content":sum(not bool(x.raw.get("qualified")) for x in records),"pagination_complete":True,
            "source_collection_complete":True,"listing_url":self.url,"attachments":len(links),
            "expired_count":sum(1 for x in records if x.status=="EXPIRED"),"unknown_status_count":sum(1 for x in records if x.status=="UNKNOWN"),"parser_version":self.parser_version}
        self.diagnostics.append(f"Parsed {len(unique)} announcement entries from KFU's official investment announcement page.")
        return records,1


class ModonAdapter(BaseSourceAdapter):
    """Monitor official MODON public pages; never treat reference GIS features as inventory."""
    key="modon"
    url="https://modon.gov.sa/en/InvestmentOpportunities"
    gis_catalog="https://gis.modon.ae/portal/sharing/rest"
    landbank_item_id="43d60e1f77804597a178b6723fe2f1dc"
    open_data_publisher_id="d7da4e5a-0671-4b32-bb48-d31d1a271fa2"
    open_data_api="https://open.data.gov.sa/data/api"
    parser_version="2026.10.12-modon-2"
    public_surfaces=(
        ("/en/Investors-Journeys","INVESTOR_JOURNEY"),("/en/InvestmentOpportunities","PUBLIC_OPPORTUNITY_CATALOG"),
        ("/en/Products-Main-Categories","PRODUCT_CATALOG"),("/en/Shareek-System","SHAREEK"),
        ("/en/Site-Map","SITE_MAP"),("/en/MODON-App","SMART_APP_INFORMATION"),
        ("/en/Services","SERVICES"),("/en/News","PUBLIC_NEWS"),
        ("/en/Main-Products/readyfactory","READY_BUILT_FACTORIES"),
        ("/ar-SA/InvestmentOpportunities","PUBLIC_OPPORTUNITY_CATALOG_AR"),
        ("/ar-SA/Investors-Journeys","INVESTOR_JOURNEY_AR"),
        ("/ar-SA/Products-Main-Categories","PRODUCT_CATALOG_AR"),
        ("/ar-SA/Site-Map","SITE_MAP_AR"),("/ar-SA/News","PUBLIC_NEWS_AR"),
        ("/en/About-Open-Data","OPEN_DATA_INFORMATION"),
        ("https://open.data.gov.sa/en/publishers/d7da4e5a-0671-4b32-bb48-d31d1a271fa2","OPEN_DATA_PUBLISHER_CATALOG"),
    )

    def __init__(self): self.metrics={};self.content_items=[];self.diagnostics=[]

    @staticmethod
    def is_al_ahsa_location(value):
        return bool(re.search(r"(?:al[ -]?ahsa|al[ -]?hasa|hofuf|al[ -]?hofuf|المبرز|الأحساء|الاحساء|الهفوف)",value or "",re.I))

    @staticmethod
    def project_fields(attributes,geometry=None):
        geometry=geometry or {}
        return {"official_source_id":attributes.get("OBJECTID"),"asset_name":attributes.get("Project") or attributes.get("Location"),
            "raw_status":attributes.get("Project_Status"),"area_sqm":attributes.get("Land_Area_sqm"),"geometry":geometry}

    @staticmethod
    def is_current_investment_product(attributes):
        """Only explicit current availability can qualify a map/catalog asset."""
        for key,value in (attributes or {}).items():
            if re.search(r"availability|available|vacant|investment.?status|product.?status",str(key),re.I):
                if isinstance(value,bool):return value
                if re.search(r"\b(?:available|vacant|open|for investment)\b|متاح|شاغر|للاستثمار",str(value or ""),re.I):return True
                if re.search(r"\b(?:unavailable|occupied|allocated|leased|closed)\b|غير متاح|مشغول|مخصص|مؤجر",str(value or ""),re.I):return False
        return False

    @staticmethod
    def public_page_was_rejected(body):
        """Some WAF denials are HTTP 200 pages; do not mistake them for empty data."""
        return bool(re.search(r"<title>\s*(?:request rejected|access denied)|requested URL was rejected",body or "",re.I))

    @staticmethod
    def dataset_is_inventory_relevant(title):
        return bool(re.search(r"industrial cit(?:y|ies)|industr(?:y|ial)|factor(?:y|ies)|warehouse|product|invest\w*|financ|allocat|logistic|data cent(?:er|re)|facilit|commercial|land",title or "",re.I))

    async def fetch(self,client):
        headers={**self.headers,"User-Agent":"Mozilla/5.0 (compatible; public opportunity monitor)","Accept-Language":"en,ar;q=0.8"}
        surface_responses=[];surface_errors=[]
        for path,kind in self.public_surfaces:
            url=urljoin("https://modon.gov.sa",path)
            response=await client.get(url,headers=headers)
            if response.is_success and not self.public_page_was_rejected(response.text):surface_responses.append((url,kind,response))
            elif response.is_success:surface_errors.append({"url":url,"status":"CONTENT_BLOCKED"})
            else:surface_errors.append({"url":url,"status":response.status_code})
        page=next((response for url,_,response in surface_responses if url.endswith("/en/InvestmentOpportunities")),None)
        if page is None:raise RuntimeError("MODON official investment opportunity page did not load")
        soup=BeautifulSoup(page.text,"html.parser")
        api_client=await client.get("https://modon.gov.sa/api/runtime-env",headers=headers)
        api_client.raise_for_status()
        api_match=re.search(r'NEXT_PUBLIC_API_ENDPOINT":"([^"]+)"',api_client.text)
        internal_api=api_match.group(1) if api_match else None
        # Validate the advertised public Landbank item against its live service schema
        # and a small sample. Do not treat unrelated project polygons as industrial stock.
        catalog=await client.get(self.gis_catalog+"/search",params={"f":"json","q":"MODON","num":100},headers=headers)
        catalog.raise_for_status();items=(catalog.json() or {}).get("results",[])
        landbank=next((x for x in items if x.get("id")==self.landbank_item_id),None)
        gis_schema=None;gis_sample=[];gis_count=None;gis_fields=[];gis_url=None
        if landbank:
            map_response=await client.get(f"{self.gis_catalog}/content/items/53a4c4b42e024bdb9a687daa3fdad90a/data",params={"f":"json"},headers=headers)
            map_response.raise_for_status();layers=(map_response.json() or {}).get("operationalLayers",[])
            gis_url=next((x.get("url") for x in layers if x.get("url")),None)
            if gis_url:
                layer_response=await client.get(gis_url.rstrip("/")+"/0",params={"f":"json"},headers=headers)
                layer_response.raise_for_status();gis_schema=layer_response.json();gis_fields=[x.get("name") for x in gis_schema.get("fields",[])]
                count_response=await client.get(gis_url.rstrip("/")+"/0/query",params={"where":"1=1","returnCountOnly":"true","f":"json"},headers=headers)
                count_response.raise_for_status();gis_count=(count_response.json() or {}).get("count")
                sample_response=await client.get(gis_url.rstrip("/")+"/0/query",params={"where":"1=1","outFields":"*","returnGeometry":"true","resultRecordCount":5,"f":"json"},headers=headers)
                sample_response.raise_for_status();gis_sample=(sample_response.json() or {}).get("features",[])
        # The portal publishes a documented, unauthenticated GET API for publisher,
        # dataset, and resource metadata. Enumerate all publisher IDs, then fetch
        # details/resources only for datasets whose titles could describe investable
        # assets or MODON product availability. File contents remain reference data.
        open_data_errors=[];open_data_calls=0;open_data_successes=0;open_data_relevant=[];open_data_records=[]
        api_headers={**headers,"Accept":"application/json","Referer":"https://open.data.gov.sa/en/"}
        organization_url=f"{self.open_data_api}/organizations"
        organization_response=await client.get(organization_url,params={"version":"-1","organization":self.open_data_publisher_id},headers=api_headers);open_data_calls+=1
        publisher_payload={}
        try:
            organization_response.raise_for_status();publisher_payload=organization_response.json();open_data_successes+=1
            if not isinstance(publisher_payload.get("datasets"),list):raise ValueError("publisher API did not return its public dataset list")
        except Exception as exc:
            open_data_errors.append({"url":str(organization_response.url),"status":getattr(organization_response,"status_code","INVALID_JSON"),"error":str(exc)})
        catalog_datasets=publisher_payload.get("datasets",[]) if isinstance(publisher_payload,dict) else []
        open_data_relevant=[x for x in catalog_datasets if self.dataset_is_inventory_relevant(x.get("titleEn") or x.get("titleAr"))]
        async def fetch_open_data_detail(item):
            dataset_id=str(item.get("id") or "");base_params={"version":"-1","dataset":dataset_id}
            detail_url=f"{self.open_data_api}/datasets";resources_url=f"{self.open_data_api}/datasets/resources"
            results=[]
            for endpoint in (detail_url,resources_url):
                response=await client.get(endpoint,params=base_params,headers=api_headers)
                if not response.is_success or "json" not in response.headers.get("content-type","").lower():
                    return item,None,None,{"url":str(response.url),"status":response.status_code,"error":"Documented public API did not return JSON"}
                try:results.append(response.json())
                except Exception as exc:return item,None,None,{"url":str(response.url),"status":response.status_code,"error":f"Invalid JSON: {exc}"}
            return item,results[0],results[1],None
        if open_data_relevant:
            results=await asyncio.gather(*(fetch_open_data_detail(item) for item in open_data_relevant))
            open_data_calls+=2*len(results)
            for item,detail,resources,error in results:
                if error:open_data_errors.append(error);continue
                open_data_successes+=2
                files=resources.get("resources",[]) if isinstance(resources,dict) else []
                open_data_records.append({"id":item.get("id"),"title":detail.get("titleEn") or item.get("titleEn"),"title_ar":detail.get("titleAr") or item.get("titleAr"),
                    "description":detail.get("descriptionEn"),"update_frequency":detail.get("updateFrequency"),"time_period":detail.get("timePeriod"),
                    "updated_at":detail.get("updatedAt"),"resources_count":detail.get("resourcesCount"),"resource_details":files,
                    "url":f"https://open.data.gov.sa/en/datasets/view/{item.get('id')}"})
        location_labels=[str((x.get("attributes") or {}).get("Location") or "") for x in gis_sample]
        has_asset_status=any(re.search(r"status|availab|product|plot|asset",str(x),re.I) for x in gis_fields)
        has_ahsa_city=any(self.is_al_ahsa_location(x) for x in location_labels)
        all_surface_errors=surface_errors+[dict(x,status=f"OPEN_DATA_{x.get('status')}") for x in open_data_errors]
        self.metrics={"source_total_reported":None,"pages_requested":len(self.public_surfaces)+2+(4 if landbank else 0)+open_data_calls,"pages_successful":len(surface_responses)+2+(4 if landbank else 0)+open_data_successes,"records_received":0,"records_parsed":0,
            "unique_records":0,"pagination_complete":False,"source_collection_complete":False,"reconciliation_safe":False,"public_scope_complete":not all_surface_errors,
            "coverage_status":"PUBLIC_COVERAGE_LIMITED","completeness_basis":"PUBLIC_COMPLETENESS","absolute_source_completeness":"UNKNOWN","technical_health":"HEALTHY" if not all_surface_errors else "WARNING",
            "investment_page_http_status":page.status_code,"public_surfaces_checked":[{"url":u,"type":k,"http_status":r.status_code} for u,k,r in surface_responses],
            "public_surface_errors":all_surface_errors,"public_landbank_item_found":bool(landbank),
            "modon_sitecore_api_origin":internal_api,"modon_sitecore_api_is_private":bool(internal_api and ".local" in urlparse(internal_api).hostname),
            "gis_layer_url":gis_url,"gis_feature_count":gis_count,"gis_fields":gis_fields,"gis_location_sample":location_labels,
            "gis_contains_al_ahsa_city_label":has_ahsa_city,"gis_has_product_or_availability_fields":has_asset_status,
            "gis_used_for_opportunities":False,"gis_exclusion_reason":"Public Landbank layer does not expose product availability/status fields and its live sample contains unrelated Hudayriyat locations, with no Al-Ahsa industrial-city evidence; excluded from opportunity ingestion.",
            "product_catalog_page":"https://modon.gov.sa/en/Products-Main-Categories","ready_built_factory_page":"https://modon.gov.sa/en/Main-Products/readyfactory",
            "open_data_publisher_id":self.open_data_publisher_id,"open_data_api_documentation":"https://open.data.gov.sa/en/datasets/view/ef32529a-4b18-4048-939b-61b083186328/api",
            "open_data_dataset_count":len(catalog_datasets),"open_data_relevant_dataset_count":len(open_data_relevant),"open_data_scan_complete":bool(catalog_datasets) and len(open_data_records)==len(open_data_relevant) and not open_data_errors,
            "open_data_catalog_datasets":catalog_datasets,"open_data_relevant_datasets":open_data_records,"open_data_errors":open_data_errors,
            "inventory_endpoint_available":False,"publicly_verified_al_ahsa_opportunities":0,"public_current_al_ahsa_opportunities":None,
            "coverage_notes":"MODON's unauthenticated public catalog and product pages, filter geography, Shareek, map/app information, news, Site Map, Arabic/English routes, and available GIS schema were checked. Public availability is not exposed as a complete live Al-Ahsa inventory; verified zero results on the live Al-Ahsa catalog filters are not interpreted as zero total MODON inventory.",
            "source_limitations":[{"limitation_type":"NO_PUBLIC_INVENTORY","description":"Public product and investment pages provide general catalog/filter information, but no complete current Al-Ahsa availability feed is exposed to the public adapter.","evidence_url":self.url,"resolution":"Continue monitoring public catalog, news, and product pages; do not reconcile or remove source records from empty catalog-shell responses."},
                {"limitation_type":"PRIVATE_API","description":"The browser runtime advertises Sitecore content/search services at a private .local host; the adapter does not query that origin.","evidence_url":"https://modon.gov.sa/api/runtime-env","resolution":"Use only publicly accessible first-party pages and endpoints."}]+([{"limitation_type":"PUBLIC_DATA_PARTIAL","description":"The documented public Open Data metadata/resource API failed for one or more catalog requests; the current dataset catalog could not be exhaustively checked in this sync.","evidence_url":"https://open.data.gov.sa/en/datasets/view/ef32529a-4b18-4048-939b-61b083186328/api","resolution":"Retry the documented unauthenticated GET API and require all relevant metadata/resources before considering the open-data monitoring scope complete."}] if open_data_errors else []),
            "product_availability":{"industrial_land":{"public_catalog":True,"location_filter":True,"al_ahsa_filter_present":True,"availability_field":False,"stable_product_id_observed":None,"application_route_observed":True,"publicly_verified_al_ahsa_opportunities":0,"current_al_ahsa_count":None},
                "ready_built_factories":{"public_catalog":True,"location_filter":True,"al_ahsa_filter_present":True,"availability_field":False,"stable_product_id_observed":None,"application_route_observed":True,"publicly_verified_al_ahsa_opportunities":0,"current_al_ahsa_count":None},
                "warehouses":{"public_catalog":True,"location_filter":True,"al_ahsa_filter_present":True,"availability_field":False,"stable_product_id_observed":None,"application_route_observed":None,"publicly_verified_al_ahsa_opportunities":0,"current_al_ahsa_count":None},
                "logistics_products":{"public_catalog":True,"location_filter":True,"al_ahsa_filter_present":True,"availability_field":False,"stable_product_id_observed":None,"application_route_observed":True,"publicly_verified_al_ahsa_opportunities":0,"current_al_ahsa_count":None},
                "commercial_products":{"public_catalog":True,"location_filter":True,"al_ahsa_filter_present":True,"availability_field":False,"stable_product_id_observed":None,"application_route_observed":None,"publicly_verified_al_ahsa_opportunities":0,"current_al_ahsa_count":None}},
            "reference_assets_discovered":gis_count,"reference_assets_ingested_as_opportunities":0,
            "gis_reference_only":True,"gis_availability_field_present":has_asset_status,"parser_version":self.parser_version}
        self.content_items=[]
        for url,kind,response in surface_responses:
            doc=BeautifulSoup(response.text,"html.parser");text_content=re.sub(r"\s+"," ",doc.get_text(" ",strip=True))[:20000]
            page_state={}
            next_data=doc.select_one("script#__NEXT_DATA__")
            if next_data:
                try:
                    props=json.loads(next_data.get_text()) .get("props",{}).get("pageProps",{})
                    route_fields=((props.get("layoutData") or {}).get("sitecore") or {}).get("route",{}).get("fields",{})
                    page_state={"componentProps":props.get("componentProps"),"filter_fields":route_fields.get("FiltersFields"),
                        "navigation_filters":route_fields.get("NavigationFilter"),"locale":props.get("locale")}
                    text_content += " Embedded SSR page data: "+json.dumps(page_state,ensure_ascii=False,sort_keys=True)[:40000]
                except (ValueError,TypeError,AttributeError):
                    page_state={"ssr_data_parse_warning":True}
            attachments=[{"filename":a.get_text(" ",strip=True) or a.get("href"),"url":urljoin(url,a.get("href","")),"type":urlparse(a.get("href","" )).path.rsplit(".",1)[-1].lower(),"downloaded":False,"checksum":None}
                         for a in doc.select('a[href]') if re.search(r"\.(?:pdf|xlsx?|csv)(?:\?|$)",a.get("href",""),re.I)]
            self.content_items.append({"url":url,"title":doc.title.get_text(" ",strip=True) if doc.title else kind,"publication_date":None,
                "content_type":kind,"raw_text":text_content,"extracted_description":text_content[:2500],"attachments":attachments,
                "detected_keywords":[],"parser_version":self.parser_version,
                "fingerprint":hashlib.sha256((response.text+json.dumps(attachments,ensure_ascii=False,sort_keys=True)).encode()).hexdigest()})
        for dataset in open_data_records:
            files=dataset.get("resource_details",[])
            self.content_items.append({"url":dataset["url"],"title":dataset["title"],"publication_date":dataset.get("updated_at"),"content_type":"OPEN_DATA_DATASET_METADATA",
                "raw_text":json.dumps(dataset,ensure_ascii=False,sort_keys=True),"extracted_description":dataset.get("description") or "",
                "attachments":[{"filename":f.get("name"),"url":f.get("downloadUrl"),"type":f.get("format"),"updated_at":f.get("updatedAt"),"downloaded":False,"checksum":None} for f in files],
                "detected_keywords":[],"parser_version":self.parser_version,"fingerprint":hashlib.sha256(json.dumps(dataset,ensure_ascii=False,sort_keys=True).encode()).hexdigest()})
        self.metrics["downloadable_datasets"]=[f.get("downloadUrl") for d in open_data_records for f in d.get("resource_details",[]) if f.get("downloadUrl")]
        self.metrics["reference_asset_classification"]="REFERENCE_ASSET_ONLY: public GIS/map features do not assert current vacancy or investor availability and are excluded from SourceOpportunity and Master Opportunity."
        self.diagnostics.append("MODON public pages, catalogs, app information, news, Shareek, bilingual routes, public GIS schema, and the documented unauthenticated open-data API were checked. Relevant dataset metadata/resources are fingerprinted, but aggregate/reference datasets are not ingested as opportunities. Public product availability is not exposed as a complete live Al-Ahsa inventory. No deletion reconciliation is performed.")
        return [],self.metrics["pages_requested"]


class NcpAdapter(BaseSourceAdapter):
    """Crawl NCP's public discovery pages and news archive; never query its private portal API."""
    key="ncp"
    url="https://ncp.gov.sa/en/MediaCenter/News/Pages/default.aspx"
    arabic_url="https://ncp.gov.sa/ar/MediaCenter/News/Pages/default.aspx"
    public_discovery_pages=(
        ("https://ncp.gov.sa/en/Pages/default.aspx","PUBLIC_HOMEPAGE"),
        ("https://ncp.gov.sa/en/MediaCenter/Pages/default.aspx","MEDIA_CENTER"),
        ("https://ncp.gov.sa/en/MediaCenter/DigitalLibrary/Pages/default.aspx","DIGITAL_LIBRARY"),
        ("https://ncp.gov.sa/en/KnowledgeCenter/Pages/default.aspx","KNOWLEDGE_CENTER"),
        ("https://ncp.gov.sa/sitemap.xml","SITEMAP"),
    )
    investor_portal="https://investors.ncp.gov.sa/home"
    fallback_public_detail_urls=("https://ncp.gov.sa/en/MediaCenter/News/Pages/FoodSafetyLabs.aspx",)
    parser_version="2026.10.12-ncp-2"
    city_terms={"al ahsa":"Al-Ahsa","al-ahsa":"Al-Ahsa","al hasa":"Al-Ahsa","hofuf":"Al-Hofuf","al hofuf":"Al-Hofuf","mubarraz":"Al-Mubarraz","الأحساء":"الأحساء","الاحساء":"الأحساء","الهفوف":"الهفوف","المبرز":"المبرز"}
    other_city_terms=("Riyadh","Jeddah","Makkah","Madinah","Taif","Tabuk","Qassim","Hafr Al Batin","Northern Borders","الرياض","جدة","مكة","المدينة","الطائف","تبوك","القصيم","حفر الباطن","الحدود الشمالية")

    def __init__(self): self.metrics={};self.content_items=[];self.diagnostics=[];self.raw_candidates=[]

    @classmethod
    def project_stage(cls,title,text):
        value=(title+" "+text).casefold()
        if re.search(r"cancelled|terminated|إلغاء المشروع|إلغاء طرح",value):return "CANCELLED"
        if re.search(r"request for proposals|\bRFP\b|طلب تقديم العروض",value):return "RFP"
        if re.search(r"request for qualification|\bRFQ\b|طلب التأهيل",value):return "RFQ"
        if re.search(r"(?:eoi|expression of interest).{0,30}(?:result|received|express interest)|(?:result|received|express interest).{0,30}(?:eoi|expression of interest)|نتائج.{0,30}إبداء الرغبة",value):return "EOI_RESULTS"
        if re.search(r"expression of interest|\bEOI\b|إبداء الرغبة",value):return "EOI"
        if re.search(r"bid phase|bid submission|bidders|مرحلة تقديم العروض",value):return "BID_STAGE"
        if re.search(r"awarded|award of|ترسية|تم الترسية",value):return "AWARDED"
        return "PIPELINE"

    @classmethod
    def locations(cls,text):
        text=text or ""
        sentences=[x.strip() for x in re.split(r"(?<=[.!?؟])\s+",text) if x.strip()]
        target_terms=tuple(cls.city_terms.keys())
        target_sentences=[s for s in sentences if any(term.casefold() in s.casefold() for term in target_terms)]
        if target_sentences:
            # Publication datelines and the issuing authority often mention other cities;
            # retain the sentence that actually states the project location.
            text=" ".join(target_sentences)
        else:
            scope_sentences=[s for s in sentences if re.search(r"project (?:scope|covers|spans|locations?|will be located)|المشروع (?:يشمل|يقع|يمتد)|مواقع المشروع",s,re.I)]
            text=" ".join(scope_sentences) if scope_sentences else text[:300]
        lower=text.casefold();found=[]
        for term,name in cls.city_terms.items():
            if term.casefold() in lower and name not in found:found.append(name)
        for name in cls.other_city_terms:
            if name.casefold() in lower and name not in found:found.append(name)
        return found

    @classmethod
    def is_ahsa_evidence(cls,locations):
        return any(x in {"Al-Ahsa","Al-Hofuf","Al-Mubarraz","الأحساء","الهفوف","المبرز"} for x in locations)

    @staticmethod
    def lifecycle(stage,deadline,today=None):
        today=today or datetime.now(timezone.utc).date().isoformat()
        if stage=="AWARDED":return "AWARDED"
        if stage=="CANCELLED":return "CANCELLED"
        if deadline and deadline < today:return "EXPIRED"
        return "UNKNOWN"

    @staticmethod
    def project_identity(title,owner=None):
        """Conservative title identity: remove lifecycle wording, preserve project core."""
        value=normalize_arabic((title or "").casefold())
        value=re.sub(r"\b(?:rfp|rfq|eoi)\b|request for (?:proposals?|qualification)|expression of interest|\b(?:launch(?:es|ed)?|announces?|announcement of|project preview|preview|qualified bidders for)\b", " ", value, flags=re.I)
        value=re.sub(r"^(?:the )?(?:ministry of [a-z ]+|[a-z ]+ municipality|ncp|momah|umm al-qura university)\s+(?:and\s+ncp\s+)?", " ", value, flags=re.I)
        value=re.sub(r"\b(?:in|across|for)\s+(?:the )?(?:eastern province|riyadh|saudi arabia)\b", " ", value, flags=re.I)
        value=re.sub(r"\b(?:ppp|project|phase|launched|launch|to|the|of|for|and)\b", " ", value, flags=re.I)
        value=re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", value).strip()
        if owner:
            owner_norm=re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", normalize_arabic(owner.casefold())).strip()
            if owner_norm and value.startswith(owner_norm):value=value[len(owner_norm):].strip()
        return value

    @staticmethod
    def _listing_rows(html):
        match=re.search(r"WPQ1ListData\s*=\s*(\{.*?\})\s*;",html,re.S)
        if not match:return [],None
        data=json.loads(match.group(1))
        return data.get("Row",[]),data.get("NextHref")

    async def _crawl_archive(self,client,listing_url,headers):
        entries=[];seen=set();next_url=listing_url;page_count=0
        while next_url and page_count<100:
            response=await client.get(next_url,headers=headers);response.raise_for_status();page_count+=1
            rows,next_href=self._listing_rows(response.text)
            if not rows:raise ValueError(f"NCP public news archive page {page_count} returned no SharePoint list data")
            for row in rows:
                path=row.get("FileRef") or ""
                if not path.lower().endswith(".aspx"):continue
                article=urljoin("https://ncp.gov.sa",path)
                if article not in seen:
                    seen.add(article);entries.append({"url":article,"title":row.get("Title") or "","publication_date":row.get("ArticleStartDate")})
            next_url=urljoin(listing_url,next_href) if next_href else None
        if next_url:raise ValueError("NCP archive pagination exceeded the safety limit")
        return entries,page_count

    async def fetch(self,client):
        headers={**self.headers,"User-Agent":"Mozilla/5.0 (compatible; public opportunity monitor)","Accept-Language":"en,ar;q=0.8"}
        discovery_responses=[];discovery_errors=[]
        for discovery_url,kind in self.public_discovery_pages:
            response=await client.get(discovery_url,headers=headers)
            if response.is_success:discovery_responses.append((discovery_url,kind,response))
            else:discovery_errors.append({"url":discovery_url,"status":response.status_code})
        archive_entries=[];archive_pages=0;archive_pages_attempted=0;archive_locale_errors=[];archive_language_completion={}
        for index,listing_url in enumerate((self.url,self.arabic_url)):
            language="en" if index==0 else "ar"
            try:
                entries,pages_scanned=await self._crawl_archive(client,listing_url,headers)
                archive_language_completion[language]=True;archive_pages_attempted+=pages_scanned;archive_pages+=pages_scanned
            except Exception as exc:
                if language=="en":raise
                # English is the canonical defined archive scope. Arabic is still crawled
                # and deduplicated where available; outages of its mirror are surfaced.
                entries=[];pages_scanned=0;archive_pages_attempted+=1;archive_language_completion[language]=False
                archive_locale_errors.append({"language":language,"url":listing_url,"error":str(exc)})
            archive_entries.extend(entries)
        unique_entries={}
        for entry in archive_entries:
            # NCP uses the same article filename on its English and Arabic archive routes.
            # Keep the English rendition when both localized links point to that identity.
            key=urlparse(entry["url"]).path.rsplit("/",1)[-1].casefold()
            unique_entries.setdefault(key,entry)
        archive_entries=list(unique_entries.values());urls=[item["url"] for item in archive_entries]
        archive_detail_links=list(urls)
        portal=await client.get(self.investor_portal,headers=headers);portal.raise_for_status()
        portal_soup=BeautifulSoup(portal.text,"html.parser")
        main_src=next((x.get("src") for x in portal_soup.select('script[src]') if re.search(r"(?:^|/)main-[^/]+\.js$",x.get("src",""),re.I)),None)
        api_base=None;portal_assets_requested=1;portal_assets_successful=1
        if main_src:
            main_response=await client.get(urljoin(self.investor_portal,main_src),headers=headers);portal_assets_requested+=1
            if main_response.is_success:
                portal_assets_successful+=1
                chunks=list(dict.fromkeys(re.findall(r"chunk-[A-Z0-9]+\.js",main_response.text)))
                async def read_config_chunk(name):
                    response=await client.get(urljoin(self.investor_portal,name),headers=headers)
                    if not response.is_success:return False,None
                    match=re.search(r"apiBaseUrl:\"([^\"]+)\"",response.text)
                    return True,match.group(1) if match else None
                # The public bundle is the only available discovery path; stop once the
                # portal's API origin is found instead of probing that origin.
                for offset in range(0,len(chunks),8):
                    group=chunks[offset:offset+8];portal_assets_requested+=len(group)
                    results=await asyncio.gather(*(read_config_chunk(name) for name in group))
                    portal_assets_successful+=sum(1 for success,_ in results if success)
                    api_base=next((value for _,value in results if value),None)
                    if api_base:break
        # The paginated public archive is the canonical announcement scope; portal
        # query-backed records are unavailable and are not inferred from its shell.
        pages=[];records=[]
        publication_by_url={item["url"]:item.get("publication_date") for item in archive_entries}
        for url in urls:
            response=await client.get(url,headers={**headers,"Referer":self.url});response.raise_for_status();doc=BeautifulSoup(response.text,"html.parser")
            meta_title=doc.select_one('meta[property="og:title"]') or doc.select_one('meta[name="title"]')
            title=(meta_title.get("content","") if meta_title else "") or (doc.title.get_text(" ",strip=True) if doc.title else "")
            if not title or title.casefold()=="news":
                title_node=next((x for x in doc.select("h2,h3,h4") if len(x.get_text(" ",strip=True))>25),None)
                title=title_node.get_text(" ",strip=True) if title_node else title
            main=doc.select_one("#DeltaPlaceHolderMain") or doc.select_one("main") or doc.body or doc
            raw_text=re.sub(r"\s+"," ",main.get_text(" ",strip=True))[:50000]
            attachments=[]
            for a in main.select("a[href]"):
                href=urljoin(url,a.get("href",""));label=a.get_text(" ",strip=True) or href.rsplit("/",1)[-1]
                if re.search(r"\.(?:pdf|docx?|xlsx?)(?:\?|$)",href,re.I):attachments.append({"filename":label,"url":href,"type":href.split("?")[0].rsplit(".",1)[-1].lower(),"downloaded":False,"checksum":None})
            stage=self.project_stage(title,raw_text);locations=self.locations(title+" "+raw_text)
            target=self.is_ahsa_evidence(locations)
            multi=target and len(locations)>1
            lifecycle="UNKNOWN"
            deadline_match=re.search(r"(?:submit|submission|deadline|by)\s+(?:their\s+)?(?:applications?\s+)?(?:by\s+)?(\d{1,2}\s+[A-Za-z]+\s+20\d{2})",raw_text,re.I)
            deadline=None
            if deadline_match:
                try:deadline=datetime.strptime(deadline_match.group(1),"%d %B %Y").date().isoformat()
                except ValueError:pass
            lifecycle=self.lifecycle(stage,deadline)
            actionable=bool(re.search(r"PPP|private.?public partnership|privatization|privatisation|investment project|investment opportunity|مشروع شراكة|تخصيص|استثماري",title+" "+raw_text,re.I))
            reason=("Official NCP announcement names Al-Ahsa as one of the project locations." if target else
                "No explicit Al-Ahsa city/site found; Eastern Province alone is insufficient.")
            project_owner=None
            owner_match=re.search(r"((?:the )?(?:Ministry of|Ministry|Municipality of|[A-Z][A-Za-z]+ Municipality|[A-Z][A-Za-z]+ University)[^,.]{2,100}?)\s+(?:\([A-Z]+\)\s+)?(?:and|in collaboration with|represented by)",raw_text)
            if owner_match:project_owner=owner_match.group(1).strip()
            pub_match=re.search(r"\b(\d{2}/\d{2}/20\d{2})\b",raw_text)
            publication_date=None
            if pub_match:
                try:publication_date=datetime.strptime(pub_match.group(1),"%d/%m/%Y").date().isoformat()
                except ValueError:pass
            if not publication_date:
                archive_date=publication_by_url.get(url)
                try:publication_date=datetime.strptime(archive_date,"%d/%m/%Y").date().isoformat() if archive_date else None
                except ValueError:publication_date=None
            record={"url":url,"title":title,"publication_date":publication_date,"content_type":"PPP_PROJECT_ANNOUNCEMENT" if actionable else "GENERAL_ANNOUNCEMENT",
                    "raw_text":raw_text,"extracted_description":raw_text[:3000],"attachments":attachments,"detected_keywords":[],"parser_version":self.parser_version,
                "fingerprint":hashlib.sha256((title+raw_text+json.dumps(attachments,ensure_ascii=False,sort_keys=True)).encode()).hexdigest(),
                "qualified":bool(actionable and target),"qualification_reason":reason,"project_stage":stage,"opportunity_locations":locations,
                "location_scope":"MULTI_LOCATION" if multi else "SINGLE_LOCATION" if target else "UNKNOWN","project_owner_candidate":project_owner,
                "region":"Eastern Province" if re.search(r"Eastern Province|المنطقة الشرقية",title+" "+raw_text,re.I) else None,
                "publication_platform":"National Center for Privatization & PPP"}
            pages.append(record)
            if actionable:
                identity=self.project_identity(title,project_owner)
                # If a title contains no stable project core, retain the article as its own record.
                external_id=("ncp:foodsafetylabs" if urlparse(url).path.casefold().endswith("/foodsafetylabs.aspx") else
                    "ncp-project:"+hashlib.sha256((identity or url).encode()).hexdigest()[:24])
                model_terms = sorted(set(match.group(0).upper() for match in re.finditer(
                    r"\b(DBFMOT|DBFOMT|DBFOM|DBFM|DBFO|EOMT|ROMT|BTO|BOOT|BOT|BOO|CONCESSION)\b",
                    raw_text, re.I)))
                model_value = model_terms[0] if len(model_terms) == 1 else None
                if not model_terms and re.search(r"\bPPP\b|public-private partnership",raw_text,re.I):
                    model_value = "PPP"
                # The parser identifies entities mentioned beside collaboration
                # language; that wording does not prove legal ownership.
                candidate=RawOpportunity(external_id=external_id,title=title,url=url,owner=None,location=", ".join(locations) if locations else None,
                    deadline=deadline,status=lifecycle,description=raw_text[:3000],
                    raw={**record,"official_source_id":external_id,"opportunity_type":"PPP_PROJECT","project_stage":stage,"normalized_lifecycle_status":lifecycle,
                        "investment_model":("EOMT" if re.search(r"equip(?:ment)?[- ]operate[- ]maintain[- ]transfer",raw_text,re.I) else model_value),
                        "investment_model_candidates":model_terms if len(model_terms)>1 else [],
                        "location_confidence_score":0.98 if target else 0.0,"location_detection_method":"EXPLICIT_CITY_LIST" if target else "UNRESOLVED",
                        "location_evidence":reason,"source_scope":"SOURCE_SCOPE_AL_AHSA" if target else None},location_source_filtered=target)
                self.raw_candidates.append(candidate)
                if candidate.raw["qualified"]:records.append(candidate)
        discovery_items=[]
        for discovery_url,kind,response in discovery_responses:
            if kind=="SITEMAP":
                doc=BeautifulSoup(response.text,"xml")
                discovered_urls=[node.get_text(strip=True) for node in doc.select("loc")]
                page_title="NCP public sitemap"
                raw_text="Public sitemap lists {} site pages; news article contents are enumerated by the paginated public SharePoint News archive. Sitemap URLs:\n{}".format(len(discovered_urls),"\n".join(discovered_urls))
                attachments=[]
            else:
                doc=BeautifulSoup(response.text,"html.parser")
                page_title=(doc.title.get_text(" ",strip=True) if doc.title else kind)
                main=doc.select_one("#DeltaPlaceHolderMain") or doc.select_one("main") or doc.body or doc
                raw_text=re.sub(r"\s+"," ",main.get_text(" ",strip=True))[:30000]
                attachments=[{"filename":a.get_text(" ",strip=True) or a.get("href"),"url":urljoin(discovery_url,a.get("href","")),"type":urlparse(a.get("href","")).path.rsplit(".",1)[-1].lower(),"downloaded":False,"checksum":None}
                    for a in main.select("a[href]") if re.search(r"\.(?:pdf|docx?|xlsx?|pptx)(?:\?|$)",a.get("href",""),re.I)]
                discovered_urls=[]
                # Media Center links to the News archive and Digital Library. The library
                # and Knowledge Center are indexed for public documents, not as project rows.
                for anchor in doc.select("a[href]"):
                    href=urljoin(discovery_url,anchor.get("href",""))
                    if urlparse(href).hostname=="ncp.gov.sa":discovered_urls.append(href)
                raw_text += "\nPublic links:\n"+"\n".join(dict.fromkeys(discovered_urls))
            discovery_items.append({"url":discovery_url,"title":page_title,"publication_date":None,"content_type":kind,
                "raw_text":raw_text,"extracted_description":raw_text[:2500],"attachments":attachments,"detected_keywords":[],
                "parser_version":self.parser_version,"fingerprint":hashlib.sha256((response.text+json.dumps(attachments,ensure_ascii=False,sort_keys=True)).encode()).hexdigest(),
                "discovered_public_urls":discovered_urls})
        self.content_items=discovery_items+pages
        if not self.content_items:
            listing_text=re.sub(r"\s+"," ",portal_soup.get_text(" ",strip=True))[:10000]
            self.content_items=[{"url":self.url,"title":"NCP public news archive","publication_date":None,
                "content_type":"PPP_PIPELINE_DISCOVERY","raw_text":listing_text or "No server-rendered project detail links were returned.",
                "extracted_description":"No public project detail links were present in the live news archive response; the investors portal API is private.",
                "attachments":[],"detected_keywords":[],"parser_version":self.parser_version,
                "fingerprint":hashlib.sha256((portal.text+str(api_base)).encode()).hexdigest()}]
        private_api=bool(api_base and re.search(r"https?://(?:10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)",api_base))
        self.raw_candidates.sort(key=lambda x:((x.raw or {}).get("publication_date") or "0000-00-00",x.url))
        project_ids={x.external_id for x in self.raw_candidates}
        lifecycle_observations=[x for x in self.raw_candidates if x.raw.get("project_stage") not in (None,"PIPELINE")]
        self.metrics={"source_total_reported":len(urls),"pages_requested":len(self.public_discovery_pages)+archive_pages_attempted+len(urls)+1+portal_assets_requested,"pages_successful":len(discovery_responses)+archive_pages+len(pages)+1+portal_assets_successful,
            "records_received":len(urls),"records_parsed":len(pages),"unique_records":len(pages),"qualified_opportunities":len(records),
            "pagination_complete":True,"source_collection_complete":True,"reconciliation_safe":False,"public_scope_complete":not discovery_errors,"technical_health":"HEALTHY" if not discovery_errors else "WARNING",
            "coverage_status":"COMPLETE_FOR_DEFINED_SCOPE","completeness_basis":"PUBLIC_COMPLETENESS","absolute_source_completeness":"UNKNOWN","coverage_notes":"The complete English NCP News archive and all linked article pages are monitored; English defines the public scope. The Arabic mirror is attempted and deduplicated where available. This covers published public announcements, not the broader investor pipeline.",
            "national_pipeline_complete":False,"public_project_count":len(project_ids),"public_project_observations":len(self.raw_candidates),
            "current_investable_public_projects":None,"lifecycle_observations":len(lifecycle_observations),
            "public_scope":"All discoverable English News SharePoint archive items and linked official article pages; English is the canonical complete scope. The Arabic mirror is retried and deduplicated when available. Only explicit project/investment notices qualify as Source Opportunities.",
            "archive_languages_crawled":["en","ar"],"archive_language_completion":archive_language_completion,"archive_locale_errors":archive_locale_errors,
            "public_discovery_surfaces":[{"url":u,"type":k,"http_status":r.status_code} for u,k,r in discovery_responses],"public_discovery_errors":discovery_errors,
            "public_archive_pages":archive_pages,"public_archive_items":len(urls),
            "investor_portal_url":self.investor_portal,"portal_accessible_without_auth":True,"investor_portal_api_available":False,
            "investor_portal_api_base":api_base,"pipeline_api_blocker":"Portal client configuration points to a private API address, not a publicly reachable endpoint." if private_api else "Public project API endpoint was not discovered from the portal's loaded bundles.",
            "private_or_authenticated_pipeline_detected":private_api,"coverage_status_private_scope":"PRIVATE_API_REQUIRED" if private_api else "UNKNOWN_COVERAGE",
            "source_limitations":[{"limitation_type":"PRIVATE_API","description":"Investor Portal public shell is reachable, but its client bundle advertises a private RFC1918 API origin for project data; no request was made to that API.","evidence_url":self.investor_portal,"resolution":"Public News archive is monitored independently. Broader investor-pipeline completeness is not claimed."}]+([{"limitation_type":"PUBLIC_DATA_PARTIAL","description":"The Arabic News archive's final continuation page returned a public maintenance response during validation; English archive pagination completed and is the canonical defined scope.","evidence_url":self.arabic_url,"resolution":"Retry Arabic mirror on the next scheduled sync."}] if archive_locale_errors else []),
            "public_news_archive_detail_links":len(archive_detail_links),"fallback_detail_pages":0,
            "public_news_detail_pages":len(pages),"discovered_article_urls":urls,"explicit_al_ahsa_matches":sum(1 for x in pages if x["qualified"]),
            "expired_count":sum(1 for x in self.raw_candidates if x.status=="EXPIRED"),"parser_version":self.parser_version}
        self.diagnostics.append("NCP public English and Arabic news archives were paginated to their end and localized copies sharing the same article filename were consolidated. Linked articles were parsed. This is complete for the defined public announcement scope; the portal's advertised private RFC1918 API is excluded, so absolute pipeline completeness is unknown.")
        return records,self.metrics["pages_requested"]


class NhcAdapter(BaseSourceAdapter):
    """Monitor only NHC's unauthenticated investment and qualification surfaces."""
    key = "nhc"
    url = "https://www.nhc.sa/en/investment-opportunities/"
    parser_version = "2026.10.12-nhc-1"
    pages = (
        ("https://www.nhc.sa/en/investment-opportunities/", "INVESTMENT_CATEGORIES"),
        ("https://www.nhc.sa/ar/investment-opportunities/", "INVESTMENT_CATEGORIES_AR"),
        ("https://nhc.sa/en/lo/", "REAL_ESTATE_STIMULATION"),
        ("https://nhc.sa/ar/lo/", "REAL_ESTATE_STIMULATION_AR"),
        ("https://investment.nhc.sa/ar/investments", "PUBLIC_INVESTOR_INTAKE"),
        ("https://investment.nhc.sa/ar/developer-qualification", "DEVELOPER_QUALIFICATION"),
    )
    route_criticality = {
        # The English page is an equivalent locale mirror. The Arabic page is the
        # canonical required category surface, so one locale being unavailable
        # does not hide a distinct opportunity population.
        "https://www.nhc.sa/en/investment-opportunities/": "SUPPORTING",
        "https://www.nhc.sa/ar/investment-opportunities/": "CRITICAL",
        "https://nhc.sa/en/lo/": "SUPPORTING",
        "https://nhc.sa/ar/lo/": "SUPPORTING",
        "https://investment.nhc.sa/ar/investments": "SUPPORTING",
        "https://investment.nhc.sa/ar/developer-qualification": "SUPPORTING",
    }
    consumer_terms = ("units for sale", "residential units", "buy a home", "احجز وحدتك", "وحدات سكنية", "للبيع")
    investor_terms = ("real estate developer", "facility operator", "retail stores", "restaurants and cafes",
                      "developer partnership", "commercial partner", "land development", "فرص استثمارية", "مشغل مرافق")

    def __init__(self):
        self.metrics={}; self.content_items=[]; self.diagnostics=[]; self.raw_candidates=[]

    @classmethod
    def classify_page(cls, title, text, url=""):
        value=(title+" "+text).casefold()
        if any(term in value for term in cls.consumer_terms): return "CONSUMER_PROPERTY_OFFERING", False
        if any(term in value for term in ("developer partnership", "private sector partner", "شريك تطوير", "شراكة استثمارية")):
            return "DEVELOPER_PARTNERSHIP", True
        if any(term in value for term in ("facility operator", "operator opportunity", "مشغل مرافق")):
            return "FACILITY_OPERATOR_OPPORTUNITY", True
        if any(term in value for term in ("start investing now", "invest now", "investment opportunity", "فرصة استثمارية")):
            if any(term in value for term in cls.investor_terms): return "INVESTMENT_OPPORTUNITY", True
        if "destination" in url.casefold() or "destination" in value:
            return "DESTINATION_INFORMATION", False
        return "MARKETING_CONTENT", False

    async def fetch(self, client):
        errors=[]; attachments=[]; listing_pages=[]; route_status={}; parser_failures=[]
        for url,kind in self.pages:
            try:
                response=await client.get(url,headers={**self.headers,"Accept-Language":"en,ar;q=0.8"})
                route_status[url]=response.status_code
                if response.status_code in (401,403,429):
                    errors.append({"url":url,"status":response.status_code,"error":"Public surface denied or rate limited; no challenge or access control was bypassed."})
                    continue
                response.raise_for_status()
            except SourceBlocked: raise
            except httpx.HTTPError as exc:
                route_status[url]=getattr(getattr(exc,"response",None),"status_code",None)
                errors.append({"url":url,"status":getattr(getattr(exc,"response",None),"status_code",None),"error":str(exc)})
                continue
            soup=BeautifulSoup(response.text,"html.parser")
            main=soup.select_one("main") or soup.select_one("#__next") or soup.body or soup
            title=(soup.select_one("h1") or soup.title)
            title=title.get_text(" ",strip=True) if title else kind
            raw_text=re.sub(r"\s+"," ",main.get_text(" ",strip=True))[:40000]
            if not raw_text:
                parser_failures.append(url)
                continue
            page_attachments=[]
            for a in main.select("a[href]"):
                href=urljoin(str(response.url),a.get("href","")); label=a.get_text(" ",strip=True)
                if re.search(r"\.(?:pdf|docx?|xlsx?|zip)(?:\?|$)",href,re.I):
                    item={"filename":label or href.rsplit("/",1)[-1],"url":href,"type":href.split("?")[0].rsplit(".",1)[-1].lower(),"downloaded":False,"checksum":None}
                    page_attachments.append(item); attachments.append(item)
            semantic,qualifies=self.classify_page(title,raw_text,str(response.url))
            if kind in ("INVESTMENT_CATEGORIES","INVESTMENT_CATEGORIES_AR","REAL_ESTATE_STIMULATION","REAL_ESTATE_STIMULATION_AR"):
                listing_pages.append(str(response.url))
            fingerprint=hashlib.sha256((title+"\n"+raw_text+json.dumps(page_attachments,ensure_ascii=False,sort_keys=True)).encode()).hexdigest()
            self.content_items.append({"url":str(response.url),"title":title,"publication_date":None,"content_type":"NHC_"+kind,
                "raw_text":raw_text,"extracted_description":raw_text[:3000],"attachments":page_attachments,
                "detected_keywords":[term for term in self.investor_terms if term.casefold() in raw_text.casefold()],
                "parser_version":self.parser_version,"fingerprint":fingerprint})
            # NHC currently publishes opportunity types and qualification steps, not separate
            # public offers with an item identity. Category copy remains source content only.
        app_page=next((x for x in self.content_items if "PUBLIC_INVESTOR_INTAKE" in x["content_type"]),None)
        app_text=(app_page or {}).get("raw_text","")
        auth_detected=bool(re.search(r"login|تسجيل الدخول|e-services|الخدمات الإلكترونية",app_text,re.I))
        route_inventory=[]
        content_by_url={item["url"]:item for item in self.content_items}
        for url,kind in self.pages:
            status=route_status.get(url)
            restricted=status in (401,403,429)
            parsed=url in content_by_url
            state=("ACCESS_RESTRICTED" if restricted else "SUCCESS" if status is not None and 200<=status<300 and parsed
                   else "PARSER_FAILED" if status is not None and 200<=status<300 else "FETCH_FAILED")
            route_inventory.append({"route_url":url,"route_name":kind,"route_type":kind,
                "route_criticality":self.route_criticality[url],"last_http_status":status,
                "route_state":state,"route_health":state,"content_role":kind,"affects_source_health":self.route_criticality[url]=="CRITICAL",
                "affects_coverage":True,"coverage_redundancy":url=="https://www.nhc.sa/en/investment-opportunities/",
                "previous_successful_content_preserved":restricted and url in content_by_url})
        critical_routes=[r for r in route_inventory if r["route_criticality"]=="CRITICAL"]
        supporting_routes=[r for r in route_inventory if r["route_criticality"]=="SUPPORTING"]
        critical_routes_successful=sum(r["route_state"]=="SUCCESS" for r in critical_routes)
        critical_ok=bool(critical_routes) and critical_routes_successful==len(critical_routes) and not parser_failures
        all_ok=critical_ok
        limitation=[{"limitation_type":"NO_PUBLIC_INVENTORY","description":"NHC's public investment page describes investor categories and qualification steps; the investment portal does not expose a current itemized opportunity inventory in the unauthenticated public view.","evidence_url":self.url,"resolution":"Monitor the official public opportunity, qualification, and stimulation pages; treat each newly published itemized partner call as an opportunity only when its identity and investor action are exposed."}]
        if auth_detected:
            limitation.append({"limitation_type":"AUTH_REQUIRED","description":"The Real Estate Stimulation service links land/e-services functions to a sign-in journey; authenticated listings are not queried.","evidence_url":"https://nhc.sa/en/lo/","resolution":"Use only unauthenticated public listing pages. No login or private endpoint is used."})
        restricted_routes=[r for r in route_inventory if r["route_state"]=="ACCESS_RESTRICTED"]
        if restricted_routes:
            limitation.append({"limitation_type":"ACCESS_RESTRICTED_SUPPORTING_ROUTE","description":"One supporting NHC public-facing English route currently returns HTTP 403. Its investment-category content is duplicated by the accessible Arabic investment-opportunities page; no unique itemized opportunity inventory is exposed there. Critical investment-information surfaces remain monitored.","evidence_url":restricted_routes[0]["route_url"],"resolution":"Retain the last successful route observation, monitor the equivalent public category page, and retry the route through ordinary unauthenticated requests; do not bypass access controls."})
        if parser_failures:
            limitation.append({"limitation_type":"PARSER_FAILURE","description":f"{len(parser_failures)} successful NHC response(s) contained no parseable page text.","evidence_url":parser_failures[0],"resolution":"Repair the public HTML parser before claiming the required route is monitored."})
        self.metrics={"technical_health":"HEALTHY" if all_ok else "WARNING","coverage_status":"PUBLIC_COVERAGE_LIMITED",
            "coverage_notes":"The public NHC scope covers investment categories and public qualification/application paths. The Arabic investment-opportunities page is the required category surface; its English equivalent is a supporting locale mirror. No current itemized Al-Ahsa investment inventory is exposed. Authenticated land/e-services are excluded.",
            "completeness_basis":"PUBLIC_COMPLETENESS","absolute_source_completeness":"UNKNOWN","public_scope_complete":all_ok,
            "source_collection_complete":all_ok,"reconciliation_safe":False,"pagination_complete":all_ok,
            "route_inventory":route_inventory,"critical_routes_total":len(critical_routes),
            "critical_routes_successful":critical_routes_successful,"supporting_routes_total":len(supporting_routes),
            "supporting_routes_successful":sum(r["route_state"]=="SUCCESS" for r in supporting_routes),
            "restricted_routes":len(restricted_routes),"parser_failures":len(parser_failures),
            "coverage_contract":"Monitor publicly accessible pages that directly describe investment categories, publicly itemized offerings when exposed, and public qualification/application pathways; do not access authenticated investor inventories.",
            "pages_requested":len(self.pages),"pages_successful":len(self.content_items),"records_received":0,"records_parsed":0,"unique_records":0,
            "public_opportunities_discovered":0,"business_qualified_opportunities":0,"consumer_listings_rejected":0,
            "qualification_documents":attachments,"public_listing_pages":listing_pages,"structured_api_discovered":False,
            "real_estate_stimulation_public":True,"real_estate_stimulation_login_required_for_eservices":auth_detected,
            "errors":errors,"public_surface_errors":errors,"source_limitations":limitation,"parser_version":self.parser_version}
        return [],len(self.pages)


class PifPrivateSectorAdapter(BaseSourceAdapter):
    """Collect the public Explore Opportunities route families; no private APIs or auth."""
    key="pif"
    url="https://www.pif.gov.sa/en/private-sector-hub/explore-opportunities/"
    company_url="https://www.pif.gov.sa/en/private-sector-hub/explore-opportunities/company-opportunities/"
    sitemap_url="https://www.pif.gov.sa/sitemap.xml"
    parser_version="2026.10.12-pif-3"
    expected_ecosystem=re.compile(r"^/en/private-sector-hub/explore-opportunities/[^/]+/$",re.I)
    known_ecosystem_slugs={"advanced-manufacturing-and-innovation","clean-energy-water-and-renewables-infrastructure",
        "industrials-and-logistics","tourism-travel-and-entertainment","urban-development-and-livability"}
    known_ecosystem_routes={
        "https://www.pif.gov.sa/en/private-sector-hub/explore-opportunities/advanced-manufacturing-and-innovation/",
        "https://www.pif.gov.sa/en/private-sector-hub/explore-opportunities/clean-energy-water-and-renewables-infrastructure/",
        "https://www.pif.gov.sa/en/private-sector-hub/explore-opportunities/industrials-and-logistics/",
        "https://www.pif.gov.sa/en/private-sector-hub/explore-opportunities/tourism-travel-and-entertainment/",
        "https://www.pif.gov.sa/en/private-sector-hub/explore-opportunities/urban-development-and-livability/",
    }
    # This route was linked from the public Explore Opportunities navigation in
    # earlier live reconnaissance. Keep it in the crawl and classify its page
    # from its own content rather than silently dropping it as an unknown slug.
    known_informational_routes={
        "https://www.pif.gov.sa/en/private-sector-hub/explore-opportunities/tasama-business-services/"
    }
    investor_action=re.compile(r"register(?:\s+your)?\s+interest|express\s+interest|apply\s+now|submit\s+interest",re.I)
    guid_pattern=re.compile(r"\{?([0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})\}?",re.I)
    def __init__(self):
        self.metrics={};self.raw_candidates=[];self.content_items=[];self.location_reviews=[];self.diagnostics=[]
        self.company_items_unverified=0;self.company_filter_mismatches=0;self.route_inventory=[];self.opportunity_observations=[]

    @staticmethod
    def item_identity(url,company,title,raw_id=None,description=None):
        if raw_id:return "pif:"+str(raw_id).strip("{}")
        # Query GUID semantics are not established by live public responses.
        # Do not promote a URL parameter to an opportunity identity.
        item="|".join(re.sub(r"\s+"," ",x or "").strip().casefold() for x in (company,title,description))
        return "pif-fp:"+hashlib.sha256(item.encode()).hexdigest()[:32]

    @staticmethod
    def _key(value):return re.sub(r"[^a-z0-9]","",str(value).casefold())

    @classmethod
    def _json_value(cls,obj,*aliases):
        if not isinstance(obj,dict):return None
        wanted={cls._key(x) for x in aliases}
        for key,value in obj.items():
            if cls._key(key) in wanted and value not in (None,""):
                if isinstance(value,dict):return value.get("value") or value.get("text") or value.get("url") or value.get("href")
                if isinstance(value,list):return "; ".join(str(x) for x in value if x not in (None,""))
                return str(value)
        return None

    @staticmethod
    def parse_sar_amount(text):
        """Return SAR min/max and source qualifier while preserving the original text."""
        if not text or re.search(r"to be updated|varies|n/?a|not available|تحدث لاحقاً|يحدد لاحقاً",text,re.I):
            return {"raw":text,"min":None,"max":None,"qualifier":"UNKNOWN"}
        value=str(text)
        sar=re.search(r"SAR\s*(.*?)(?=\s+(?:USD|\$)|$)",value,re.I)
        if sar:value=sar.group(1)
        elif "$" in value or re.search(r"\bUSD\b",value,re.I):
            value=re.split(r"\$|\bUSD\b",value,maxsplit=1,flags=re.I)[0]
        nums=[float(x.replace(",","")) for x in re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d+)?",value)]
        if not nums:return {"raw":text,"min":None,"max":None,"qualifier":"UNKNOWN"}
        unit=re.search(r"(?<![a-z])(bn|billion|mn|million|m|b)\b",value,re.I)
        factor=1.0
        if unit:
            factor=1_000_000_000.0 if unit.group(1).casefold() in ("bn","billion","b") else 1_000_000.0
        qualifier="APPROXIMATE" if re.search(r"~|approximately|approx\.?",value,re.I) else "RANGE" if len(nums)>1 else "PLUS" if re.search(r"\+",value) else "EXACT"
        return {"raw":text,"min":min(nums)*factor,"max":max(nums)*factor,"qualifier":qualifier}

    @staticmethod
    def parse_money(text):
        parsed=PifPrivateSectorAdapter.parse_sar_amount(text)
        return parsed["min"],parsed["max"]

    @staticmethod
    def item_semantic(title,description):
        value=(title+" "+description).casefold()
        if re.search(r"procurement|tender|request for quotation|rfq",value):return "PROCUREMENT_LIKE"
        if re.search(r"partner|partnership|joint venture|شراكة",value):return "PARTNERSHIP"
        if re.search(r"locali[sz]|manufactur|facility|plant|factory",value):return "MANUFACTURING" if re.search(r"manufactur|plant|factory",value) else "LOCALIZATION"
        if re.search(r"supply chain|supplier|supply of|توريد",value):return "SUPPLY_CHAIN"
        return "INVESTMENT"

    @classmethod
    def _json_payloads(cls,soup):
        payloads=[];decoder=json.JSONDecoder()
        for script in soup.select("script"):
            text=script.string or script.get_text()
            if not text.strip():continue
            candidates=[text.strip()]
            for marker in ("__NEXT_DATA__","__NUXT__","__INITIAL_STATE__","__APOLLO_STATE__","pageState","layoutData"):
                marker_pos=text.find(marker)
                if marker_pos>=0:
                    brace=min([x for x in (text.find("{",marker_pos),text.find("[",marker_pos)) if x>=0] or [-1])
                    if brace>=0:
                        try:
                            payload,_=decoder.raw_decode(text[brace:]);payloads.append(payload)
                        except json.JSONDecodeError:pass
            for candidate in candidates:
                try:payload=json.loads(candidate)
                except (json.JSONDecodeError,TypeError):continue
                if isinstance(payload,str):
                    try:payload=json.loads(payload)
                    except (json.JSONDecodeError,TypeError):pass
                payloads.append(payload)
        for node in soup.select("[data-opportunity], [data-item], [data-props]"):
            for attr in ("data-opportunity","data-item","data-props"):
                value=node.get(attr)
                if not value:continue
                try:payload=json.loads(value)
                except (json.JSONDecodeError,TypeError):continue
                payloads.append(payload)
        return payloads

    @classmethod
    def _walk_opportunity_objects(cls,value):
        if isinstance(value,dict):
            title=cls._json_value(value,"title","opportunityTitle","name")
            description=cls._json_value(value,"description","opportunityDescription","descriptionOfInvestmentOpportunity")
            item_fields={cls._key(k) for k in value}
            item_markers={cls._key(k) for k in ("descriptionOfInvestmentOpportunity","opportunityDescription","opportunityRationale",
                "indicativeInvestmentSize","investmentSize","portfolioCompany","registerInterest","opportunityId","cmsItemId",
                "indicativeAddressableDemand","addressableDemand","growthDrivers","strategicBenefits")}
            if title and description and item_fields.intersection(item_markers):
                yield value
            for child in value.values():yield from cls._walk_opportunity_objects(child)
        elif isinstance(value,list):
            for child in value:yield from cls._walk_opportunity_objects(child)

    @classmethod
    def _json_item(cls,obj,page_url,ecosystem,route_type,requested_company_filter):
        title=cls._json_value(obj,"title","opportunityTitle","name")
        if not title:return None
        company=cls._json_value(obj,"portfolioCompany","associatedCompany","company")
        description=cls._json_value(obj,"descriptionOfInvestmentOpportunity","opportunityDescription","description")
        context=cls._json_value(obj,"context","opportunityContext")
        rationale=cls._json_value(obj,"opportunityRationale","rationale")
        benefits=cls._json_value(obj,"strategicBenefits","strategicBenefit")
        drivers=cls._json_value(obj,"growthDrivers","keyGrowthDrivers")
        investment=cls._json_value(obj,"indicativeInvestmentSize","investmentSize","investmentSizeRaw")
        demand=cls._json_value(obj,"indicativeAddressableDemand","addressableDemand","addressableDemandRaw")
        register=cls._json_value(obj,"registerInterest","registerInterestUrl","interestRegistrationUrl")
        detail=cls._json_value(obj,"detailUrl","opportunityUrl","url","canonicalUrl")
        raw_id=cls._json_value(obj,"guid","opportunityId","itemId","id","cmsItemId")
        location=cls._json_value(obj,"location","city","projectLocation","locationRaw")
        source_ecosystem=cls._json_value(obj,"ecosystem","ecosystemName","category") or ecosystem
        raw_id=cls.guid_pattern.search(raw_id or "").group(1).upper() if cls.guid_pattern.search(raw_id or "") else raw_id
        return cls._finish_item(title,page_url,ecosystem,route_type,requested_company_filter,company,description,context,rationale,
            benefits,drivers,investment,demand,register,detail,raw_id,location,source_ecosystem,json.dumps(obj,ensure_ascii=False,default=str))

    @classmethod
    def _section(cls,text,label,next_labels):
        ends="|".join(re.escape(x) for x in next_labels)
        match=re.search(rf"{re.escape(label)}\s*[:\-]?\s*(.+?)(?=\s+(?:{ends})\s*[:\-]?|$)",text,re.I)
        return re.sub(r"\s+"," ",match.group(1)).strip() if match else None

    @classmethod
    def _finish_item(cls,title,page_url,route_ecosystem,route_type,requested_company_filter,company,description,context,rationale,
        benefits,drivers,investment,demand,register,detail,raw_id,location,source_ecosystem,raw_text):
        inv=cls.parse_sar_amount(investment);dem=cls.parse_sar_amount(demand)
        semantic=cls.item_semantic(title," ".join(x or "" for x in (description,context,rationale,benefits,drivers)))
        interest=urljoin(page_url,register) if register else None
        detail_url=urljoin(page_url,detail) if detail else None
        raw_id_type="official_or_cms_id" if raw_id else "fingerprint"
        fingerprint_basis="|".join(re.sub(r"\s+"," ",x or "").strip().casefold() for x in (company,title,description,context))
        identity=cls.item_identity(detail_url or page_url,company,title,raw_id,fingerprint_basis)
        if not description:description=raw_text
        return {"external_id":identity,"pif_opportunity_id":raw_id or identity.split(":",1)[-1],"pif_opportunity_id_type":raw_id_type,
            "title":title,"company":company,"ecosystem":source_ecosystem,"route_ecosystem":route_ecosystem,"semantic":semantic,
            "description":description,"context":context,"rationale":rationale,"strategic_benefits":benefits,"growth_drivers":drivers,
            "investment_size_raw":investment,"investment_size_min_sar":inv["min"],"investment_size_max_sar":inv["max"],
            "investment_size_qualifier":inv["qualifier"],"addressable_demand_raw":demand,"addressable_demand_min_sar":dem["min"],
            "addressable_demand_max_sar":dem["max"],"addressable_demand_qualifier":dem["qualifier"],"location":location,
            "interest_url":interest,"detail_url":detail_url,"source_route":page_url,"requested_company_filter":requested_company_filter,
            "actual_item_portfolio_company":company,"route_type":route_type,"raw_id":raw_id,"raw_text":raw_text,
            "route_memberships":[{"route_type":route_type,"route_url":page_url,"ecosystem":route_ecosystem,
                "requested_company_filter":requested_company_filter,"actual_item_portfolio_company":company}],
            "source_observations":[{"route_url":page_url,"route_type":route_type,"requested_company_filter":requested_company_filter,
                "actual_item_portfolio_company":company,"ecosystem":route_ecosystem,"raw_content":raw_text}]}

    def _parse_html_cards(self,soup,page_url,company_filter,ecosystem,route_type):
        cards=[];seen=set()
        for heading in soup.find_all(["h2","h3","h4"]):
            title=heading.get_text(" ",strip=True)
            if not title:continue
            node=heading
            for _ in range(8):
                node=node.parent
                if node is None:break
                content=re.sub(r"\s+"," ",node.get_text(" ",strip=True))
                if 80<=len(content)<=30000 and (self.investor_action.search(content) or "Description of Investment Opportunity" in content):break
            if node is None or len(content)<80 or content in seen:continue
            # Do not let a page-level wrapper spanning multiple opportunity headings become one card.
            if len(node.select("h2,h3,h4"))>2:continue
            # Global menus and filter panels may contain interest links. A card
            # needs the investment-description label and its own action link.
            if not re.search(r"Description of Investment Opportunity\s*[:\-]?",content,re.I):continue
            seen.add(content)
            links=[(a.get_text(" ",strip=True),urljoin(page_url,a.get("href",""))) for a in node.select("a[href]")]
            action=next((href for label,href in links if self.investor_action.search(label)),None)
            if not action:continue
            title_link=next((href for label,href in links if label.strip()==title),None)
            data_id=next((str(node.get(k)) for k in ("data-guid","data-id","data-item-id","id") if node.get(k)),None)
            def section(label,*next_labels):return self._section(content,label,next_labels)
            company=section("Portfolio Company","Register your interest","Register Interest","Indicative investment size","Description of Investment Opportunity")
            description=section("Description of Investment Opportunity","Opportunity Rationale","Strategic Benefits","Strategic benefits","Growth drivers","Key Growth Drivers","Indicative investment size","Indicative addressable demand","Register your interest")
            context=section("Context","Description of Investment Opportunity","Opportunity Rationale","Strategic Benefits","Strategic benefits","Growth drivers","Key Growth Drivers")
            rationale=section("Opportunity Rationale","Strategic Benefits","Strategic benefits","Growth drivers","Key Growth Drivers","Indicative investment size")
            benefits=section("Strategic Benefits","Strategic benefits","Key Growth Drivers","Growth drivers","Indicative investment size")
            drivers=section("Key Growth Drivers","Growth drivers","Indicative investment size","Indicative addressable demand")
            investment=section("Indicative investment size","Indicative addressable demand","Register your interest")
            demand=section("Indicative addressable demand","Register your interest")
            location=section("Location","City","الموقع","مدينة","Asset Type","Land Area")
            cards.append(self._finish_item(title,page_url,ecosystem,route_type,company_filter,company,description,context,rationale,
                benefits,drivers,investment,demand,action,title_link,data_id,location,ecosystem,content))
        return cards

    def _parse_items(self,soup,page_url,company_filter=None,ecosystem=None,route_type="ECOSYSTEM"):
        rows=self._parse_html_cards(soup,page_url,company_filter,ecosystem,route_type)
        for payload in self._json_payloads(soup):
            for obj in self._walk_opportunity_objects(payload):
                item=self._json_item(obj,page_url,ecosystem,route_type,company_filter)
                if item:rows.append(item)
        unique=[];seen=set()
        for item in rows:
            if item["external_id"] in seen:continue
            seen.add(item["external_id"]);unique.append(item)
        return unique

    @staticmethod
    def _route_type(url):
        parsed=urlparse(url);query=parse_qs(parsed.query)
        if "company-opportunities" in parsed.path:
            return "OPPORTUNITY_DETAIL" if query.get("opportunity") else "COMPANY"
        if query.get("opportunity"):return "OPPORTUNITY_DETAIL"
        return "UNKNOWN"

    def _discover_routes(self,soup,base_url):
        routes={}
        for url in self.known_ecosystem_routes:routes[url]={"route_type":"ECOSYSTEM","ecosystem":urlparse(url).path.rstrip("/").rsplit("/",1)[-1]}
        for url in self.known_informational_routes:routes[url]={"route_type":"INFORMATIONAL"}
        unknown=set();pagination=set();load_more=[]
        for anchor in soup.select("a[href]"):
            href=urljoin(base_url,anchor.get("href",""));parsed=urlparse(href)
            if parsed.hostname not in ("www.pif.gov.sa","pif.gov.sa"):continue
            if not parsed.path.startswith("/en/private-sector-hub/explore-opportunities"):continue
            label=anchor.get_text(" ",strip=True)
            if re.search(r"(?:page|paged|pageindex|pageid)=",parsed.query,re.I):pagination.add(href)
            elif parsed.path.rstrip("/").rsplit("/",1)[-1] in self.known_ecosystem_slugs:
                routes[href]={"route_type":"ECOSYSTEM","ecosystem":parsed.path.rstrip("/").rsplit("/",1)[-1]}
            elif "company-opportunities" in parsed.path and "associatedcompany" in parse_qs(parsed.query):
                routes[href]={"route_type":"OPPORTUNITY_DETAIL" if "opportunity" in parse_qs(parsed.query) else "COMPANY",
                    "requested_company_filter":parse_qs(parsed.query).get("associatedcompany",[None])[0]}
            elif "company-opportunities" in parsed.path:
                routes[href]={"route_type":"COMPANY"}
            elif "opportunity" in parse_qs(parsed.query):routes[href]={"route_type":"OPPORTUNITY_DETAIL"}
            elif parsed.path.rstrip("/")==urlparse(self.url).path.rstrip("/"):routes[href]={"route_type":"AGGREGATE_LISTING"}
            elif re.search(r"/investor-interest(?:/|$)|/register-interest(?:/|$)",parsed.path,re.I):routes[href]={"route_type":"REGISTER_INTEREST"}
            elif parsed.path.rstrip("/")!=urlparse(self.url).path.rstrip("/") and parsed.path.rstrip("/").rsplit("/",1)[-1]!="company-opportunities":
                routes[href]={"route_type":"INFORMATIONAL"}
        for button in soup.select("button,[role=button]"):
            label=(button.get_text(" ",strip=True)+" "+str(button.get("aria-label",""))).strip()
            if re.search(r"load more|show more|next|المزيد",label,re.I):
                target=button.get("data-url") or button.get("data-href") or button.get("href")
                if target:pagination.add(urljoin(base_url,target))
                else:load_more.append(label)
        return routes,sorted(unknown),sorted(pagination),load_more

    async def _request(self,client,url):
        response=await client.get(url,headers={**self.headers,"Accept-Language":"en,ar;q=0.8"})
        return response

    async def fetch(self,client):
        self._seen_items={};self.raw_candidates=[];self.content_items=[];self.location_reviews=[]
        self.company_items_unverified=0;self.company_filter_mismatches=0;self.route_inventory=[];self.opportunity_observations=[]
        errors=[];pages=[];route_response={};unclassified=[];pagination_urls=set();load_more=[]
        initial=[]
        try:
            landing=await self._request(client,self.url);initial.append((self.url,"AGGREGATE_LISTING",None,None,None))
            if landing.status_code==200:
                pages.append((str(landing.url),landing.text,"AGGREGATE_LISTING"));root=BeautifulSoup(landing.text,"html.parser")
                discovered,unclassified,initial_pagination,load_more=self._discover_routes(root,str(landing.url))
                pagination_urls.update(initial_pagination)
                for u,v in discovered.items():route_response[u]=v
            else:
                errors.append({"url":self.url,"status":landing.status_code,"error":"PIF public page was denied; no challenge or access-control bypass was attempted."})
                root=BeautifulSoup("","html.parser")
                for u in self.known_ecosystem_routes:route_response[u]={"route_type":"ECOSYSTEM","ecosystem":urlparse(u).path.rstrip("/").rsplit("/",1)[-1]}
                route_response[self.company_url]={"route_type":"COMPANY"}
                for u in self.known_informational_routes:route_response[u]={"route_type":"INFORMATIONAL"}
        except httpx.HTTPError as exc:
            errors.append({"url":self.url,"status":getattr(getattr(exc,"response",None),"status_code",None),"error":str(exc)})
            root=BeautifulSoup("","html.parser")
            for u in self.known_ecosystem_routes:route_response[u]={"route_type":"ECOSYSTEM","ecosystem":urlparse(u).path.rstrip("/").rsplit("/",1)[-1]}
            route_response[self.company_url]={"route_type":"COMPANY"}
            for u in self.known_informational_routes:route_response[u]={"route_type":"INFORMATIONAL"}
        # The sitemap is an independent public route inventory check, not an alternate data source.
        sitemap_complete=False
        try:
            sitemap=await self._request(client,self.sitemap_url)
            if sitemap.status_code==200:
                sitemap_complete=True
                xml=BeautifulSoup(sitemap.text,"xml")
                for loc in xml.find_all("loc"):
                    href=loc.get_text(strip=True);parsed=urlparse(href)
                    if parsed.hostname not in ("www.pif.gov.sa","pif.gov.sa") or "/en/private-sector-hub/explore-opportunities" not in parsed.path:continue
                    if parsed.path.rstrip("/").rsplit("/",1)[-1] in self.known_ecosystem_slugs:
                        route_response[href]={"route_type":"ECOSYSTEM","ecosystem":parsed.path.rstrip("/").rsplit("/",1)[-1]}
                    elif "company-opportunities" in parsed.path:route_response[href]={"route_type":"COMPANY","requested_company_filter":parse_qs(parsed.query).get("associatedcompany",[None])[0]}
                    elif "opportunity" in parse_qs(parsed.query):route_response[href]={"route_type":"OPPORTUNITY_DETAIL"}
                    elif parsed.path.rstrip("/")==urlparse(self.url).path.rstrip("/"):route_response[href]={"route_type":"AGGREGATE_LISTING"}
                    elif re.search(r"/investor-interest(?:/|$)|/register-interest(?:/|$)",parsed.path,re.I):route_response[href]={"route_type":"REGISTER_INTEREST"}
                    else:route_response[href]={"route_type":"INFORMATIONAL"}
            else:errors.append({"url":self.sitemap_url,"status":sitemap.status_code,"error":"Public sitemap route was not available to the crawler."})
        except httpx.HTTPError as exc:errors.append({"url":self.sitemap_url,"status":getattr(getattr(exc,"response",None),"status_code",None),"error":str(exc)})
        pending_routes=list(sorted(route_response));scanned_routes=set()
        while pending_routes:
            url=pending_routes.pop(0)
            if url in scanned_routes or url==self.url:continue
            scanned_routes.add(url)
            meta=route_response[url];route_type=meta["route_type"]
            try:
                response=await self._request(client,url)
                if response.status_code!=200:
                    errors.append({"url":url,"status":response.status_code,"error":"Public route could not be fetched; no challenge or access-control bypass was attempted."});continue
                pages.append((url,response.text,route_type));soup=BeautifulSoup(response.text,"html.parser")
                extra,extra_unknown,extra_pagination,extra_load_more=self._discover_routes(soup,url)
                for child,child_meta in extra.items():
                    if child not in route_response:
                        route_response[child]=child_meta;pending_routes.append(child)
                unclassified.extend(extra_unknown);pagination_urls.update(extra_pagination);load_more.extend(extra_load_more)
                for child in sorted(extra_pagination):
                    if child not in route_response:
                        route_response[child]={"route_type":"AGGREGATE_LISTING"};pending_routes.append(child)
                company_filter=meta.get("requested_company_filter")
                ecosystem=meta.get("ecosystem")
                items=[] if route_type=="REGISTER_INTEREST" else self._parse_items(soup,url,company_filter,ecosystem,route_type)
                if route_type=="INFORMATIONAL" and items:
                    route_type="AGGREGATE_LISTING"
                    meta["route_type"]=route_type
                    for item in items:
                        item["route_type"]=route_type
                        for membership in item["route_memberships"]:membership["route_type"]=route_type
                        for observation in item["source_observations"]:observation["route_type"]=route_type
                # Query company filters are contextual evidence only; record the actual item owner.
                for item in items:
                    actual=item.get("actual_item_portfolio_company")
                    if company_filter and actual:
                        if normalize_arabic(actual)!=normalize_arabic(company_filter):self.company_filter_mismatches+=1
                    elif company_filter and not actual:self.company_items_unverified+=1
                    self.opportunity_observations.append(item)
            except httpx.HTTPError as exc:errors.append({"url":url,"status":getattr(getattr(exc,"response",None),"status_code",None),"error":str(exc)})
        # Retain any pagination route that was discovered but could not be queued
        # after its page failed; failures stay visible in the incomplete report.
        for url in sorted(pagination_urls):
            if url not in route_response:route_response[url]={"route_type":"AGGREGATE_LISTING"}
        # Reconcile observations only by source ID/fingerprint; preserve every route membership.
        unique={}
        for item in self.opportunity_observations:
            row=unique.get(item["external_id"])
            if row is None:unique[item["external_id"]]=item
            else:
                row["route_memberships"].extend(x for x in item["route_memberships"] if x not in row["route_memberships"])
                row["source_observations"].extend(item["source_observations"])
                for key,value in item.items():
                    if row.get(key) in (None,"") and value not in (None,""):row[key]=value
        accepted=[];national=0;excluded_procurement=0;companies=set();ecosystems=set();location_reviews=[]
        for item in unique.values():
            company=item.get("company")
            if company:companies.add(company)
            if item.get("ecosystem"):ecosystems.add(item["ecosystem"])
            loc=item.get("location");relevant,confidence,city,method=classify_location(loc,item["title"],item.get("description"),item.get("context"),item.get("rationale"))
            if not relevant:national+=1
            if item["semantic"]=="PROCUREMENT_LIKE":excluded_procurement+=1
            route_memberships=item["route_memberships"]
            raw_data={"record_semantic_type":"INVESTMENT_OPPORTUNITY" if item["semantic"]!="PROCUREMENT_LIKE" else "PROCUREMENT_LIKE",
                "opportunity_type":item["semantic"],"publication_platform":"PIF Private Sector Hub","portfolio_company":company,
                "source_ecosystem":item.get("ecosystem"),"normalized_sector":None,"investment_portfolio":None,
                "context":item.get("context"),"description":item.get("description"),"opportunity_rationale":item.get("rationale"),
                "strategic_benefits":item.get("strategic_benefits"),"growth_drivers":item.get("growth_drivers"),
                "investment_size_raw":item.get("investment_size_raw"),"investment_size_min_sar":item.get("investment_size_min_sar"),
                "investment_size_max_sar":item.get("investment_size_max_sar"),"investment_size_qualifier":item.get("investment_size_qualifier"),
                "addressable_demand_raw":item.get("addressable_demand_raw"),"addressable_demand_min_sar":item.get("addressable_demand_min_sar"),
                "addressable_demand_max_sar":item.get("addressable_demand_max_sar"),"addressable_demand_qualifier":item.get("addressable_demand_qualifier"),
                "location_raw":loc,"location_confidence_score":confidence,"location_detection_method":method,
                "location_evidence":" | ".join(x for x in (loc,item["title"],item.get("description")) if x),
                "source_scope":"SOURCE_SCOPE_AL_AHSA" if relevant else None,"qualification_review_required":item["semantic"]=="PROCUREMENT_LIKE",
                "qualification_reason":"Routine procurement-like content is not promoted as an investment opportunity." if item["semantic"]=="PROCUREMENT_LIKE" else "Public Private Sector Hub item with opportunity details and investor action.",
                "pif_opportunity_id":item["pif_opportunity_id"],"pif_opportunity_id_type":item["pif_opportunity_id_type"],
                "register_interest_url":item.get("interest_url"),"detail_url":item.get("detail_url"),"source_route":item["source_route"],
                "requested_company_filter":item.get("requested_company_filter"),"actual_item_portfolio_company":company,
                "route_memberships":route_memberships,"source_observations":item.get("source_observations"),"raw_card_text":item.get("raw_text")}
            candidate=RawOpportunity(external_id=item["external_id"],title=item["title"],url=item.get("detail_url") or item["source_route"],
                # The portfolio company is retained in raw_data as a related
                # entity; the public card does not explicitly identify the owner.
                owner=None,location=loc,description=item.get("description") or item.get("context"),raw=raw_data)
            self.raw_candidates.append(candidate)
            if method=="province_only_not_qualified" and item["semantic"]!="PROCUREMENT_LIKE":
                location_reviews.append({"external_id":candidate.external_id,"title":item["title"],"sector":item["semantic"],"location":loc,
                    "description":candidate.description,"evidence":loc or "Eastern Province only","confidence_score":confidence,
                    "reason":"A specific public investment opportunity was found, but Eastern Province alone does not establish Al-Ahsa relevance."})
            if relevant and item["semantic"]!="PROCUREMENT_LIKE":accepted.append(candidate)
        self.location_reviews=location_reviews
        self.content_items=[{"url":url,"title":(BeautifulSoup(text,"html.parser").title.get_text(" ",strip=True) if BeautifulSoup(text,"html.parser").title else kind),
            "publication_date":None,"content_type":"PIF_"+kind,"raw_text":re.sub(r"\s+"," ",BeautifulSoup(text,"html.parser").get_text(" ",strip=True))[:30000],
            "extracted_description":"Public PIF Private Sector Hub route payload.","attachments":[],"detected_keywords":[],"parser_version":self.parser_version,
            "fingerprint":hashlib.sha256(text.encode()).hexdigest()} for url,text,kind in pages]
        route_types={u:m["route_type"] for u,m in route_response.items()}
        company_routes=[u for u,t in route_types.items() if t in ("COMPANY","OPPORTUNITY_DETAIL") and "company-opportunities" in urlparse(u).path]
        company_filter_routes=[u for u in company_routes if "associatedcompany" in parse_qs(urlparse(u).query)]
        ecosystem_routes=[u for u,t in route_types.items() if t=="ECOSYSTEM"]
        # Filtered company URLs are contextual only. Item ownership comes from
        # current item data, never from a requested URL parameter.
        failed_urls={row.get("url") for row in errors}
        route_errors=bool(errors)
        pagination_complete=(not load_more and all(url in scanned_routes and url not in failed_urls for url in pagination_urls))
        no_unknown=not set(unclassified)
        # A public company roster is not exposed by the current listing shell.
        # Monitoring its base route is still a successful probe; lack of an
        # enumerable roster limits coverage, not adapter health.
        required_routes=self.known_ecosystem_routes | {self.company_url} | self.known_informational_routes
        scanned_urls={url for url,_,_ in pages}
        required_routes_scanned=required_routes.issubset(scanned_urls)
        listing_states=[]
        for url,text,kind in pages:
            if kind not in ("ECOSYSTEM","COMPANY","OPPORTUNITY_DETAIL","AGGREGATE_LISTING"):continue
            soup=BeautifulSoup(text,"html.parser")
            page_text=re.sub(r"\s+"," ",soup.get_text(" ",strip=True))
            has_listing_shell=bool(re.search(r"List of Opportunities|Explore Opportunities",page_text,re.I))
            has_empty_marker=bool(re.search(r"\b(?:No results found|No portfolio found)\b",page_text,re.I))
            item_count=len(self._parse_items(soup,url,route_type=kind))
            state="ITEMS_VISIBLE" if item_count else "NO_RESULTS" if has_listing_shell and has_empty_marker else "PAGE_AVAILABLE_NO_ITEM_DATA" if has_listing_shell else "UNEXPECTED_LISTING_PAGE"
            listing_states.append({"url":url,"route_type":kind,"state":state,"items":item_count})
        listing_monitor_valid=bool(listing_states) and all(row["state"] in ("ITEMS_VISIBLE","NO_RESULTS") for row in listing_states)
        monitor_complete=(bool(pages) and required_routes_scanned and len(ecosystem_routes)==len(self.known_ecosystem_slugs)
            and not route_errors and pagination_complete and no_unknown and listing_monitor_valid)
        population_enumerable=False
        traversal_complete=False
        limitations=[]
        if route_errors:
            limitations.append({"limitation_type":"PUBLIC_ROUTE_FETCH_FAILURE","description":f"{len(errors)} public PIF route(s), including the collection root or sitemap, could not be fetched; current route inventory and opportunity population are incomplete.","evidence_url":self.url,"resolution":"Retry standard unauthenticated requests when the public site responds; do not bypass Cloudflare or infer an empty listing."})
        if not company_filter_routes:
            limitations.append({"limitation_type":"PUBLIC_COMPANY_ROSTER_NOT_EXPOSED","description":"The current public company-opportunities page is reachable and monitored, but its roster does not expose deterministic company filter values or item routes.","evidence_url":self.company_url,"resolution":"Continue monitoring the public page and enumerate company filters only when PIF exposes them through public navigation, HTML, or payload data."})
        empty_result_routes=[url for url,text,_ in pages if re.search(r"\bno results found\b",BeautifulSoup(text,"html.parser").get_text(" ",strip=True),re.I)]
        if empty_result_routes and not self.opportunity_observations:
            limitations.append({"limitation_type":"PUBLIC_LISTING_ITEMS_NOT_EXPOSED","description":f"{len(empty_result_routes)} current public listing route(s) returned a valid No results found state and no item cards or structured opportunity payload. Official PIF search-index evidence contains item-level content, but the current route representations do not expose it; index-only items are not treated as current records.","evidence_url":empty_result_routes[0],"resolution":"Keep monitoring the defined public routes and reconcile the population if item cards or a public listing payload reappear."})
        if unclassified:
            limitations.append({"limitation_type":"UNCLASSIFIED_PUBLIC_ROUTES","description":f"{len(set(unclassified))} public Explore Opportunities route(s) remain unclassified: {', '.join(sorted(set(unclassified))[:5])}","evidence_url":self.url,"resolution":"Classify each discovered route from its public page content before claiming route-family completeness."})
        if not pagination_complete:
            limitations.append({"limitation_type":"PUBLIC_PAGINATION_UNEXHAUSTED","description":f"Public pagination routes={len(pagination_urls)}; Load More controls without discoverable URLs={len(load_more)}.","evidence_url":self.url,"resolution":"Exhaust all linked public pages or implement the observed public Load More action without bypassing access controls."})
        multi_route=len(self.opportunity_observations)-len(unique)
        self.route_inventory=[{"url":u,"route_type":route_types.get(u,"UNKNOWN"),"reachable_from_public_navigation":u!=self.url,"http_status":next((200 for p in pages if p[0]==u),None)} for u in sorted(set(route_types)|set(unclassified))]
        self.metrics={"technical_health":"HEALTHY" if monitor_complete else "WARNING","coverage_status":"COMPLETE_FOR_DEFINED_SCOPE" if population_enumerable else "PUBLIC_COVERAGE_LIMITED",
            "coverage_notes":"Monitoring covers the publicly accessible Explore Opportunities landing page, all five discoverable ecosystem routes, the public company-opportunities route, linked public routes, and current content those routes expose without authentication. PIF-controlled search-index/historical content indicates a broader item population has existed, but no deterministic current public inventory or company roster is exposed.",
            "completeness_basis":"PUBLIC_ROUTE_MONITORING","absolute_source_completeness":"UNKNOWN","public_scope_complete":monitor_complete,
            "source_collection_complete":population_enumerable,"collection_incomplete":not monitor_complete,"reconciliation_safe":False,
            "public_route_monitor_complete":monitor_complete,"current_listing_states":listing_states,
            "current_listing_state":"CURRENT_PUBLIC_LISTINGS_EMPTY" if listing_monitor_valid and not self.opportunity_observations else "CURRENT_PUBLIC_LISTINGS_WITH_ITEMS" if self.opportunity_observations else "PARSER_OR_ROUTE_UNCERTAIN",
            "current_population_state":"INDEXED_OR_HISTORICAL_ITEMS_ONLY" if not self.opportunity_observations else "PUBLIC_ITEMS_VISIBLE_BUT_NOT_ENUMERABLE",
            "current_population_enumerable":population_enumerable,"company_filter_roster_public":bool(company_filter_routes),
            "required_public_routes_scanned":required_routes_scanned,
            "pagination_complete":pagination_complete,"pages_requested":2+sum(1 for url in route_response if url!=self.url),"pages_successful":len(pages),
            "records_received":len(self.opportunity_observations),"records_parsed":len(self.opportunity_observations),"unique_records":len(self.raw_candidates),
            "public_routes_scanned":len(pages),"ecosystems_scanned":len(ecosystem_routes),"company_routes_scanned":len(company_routes),
            "portfolio_companies_identified":len(companies),"company_filter_routes_scanned":len(company_filter_routes),"unique_ecosystems":len(ecosystems),"empty_result_routes":len(empty_result_routes),"item_bearing_routes":0 if not self.opportunity_observations else len({o.get("route_url") for o in self.opportunity_observations}),"raw_opportunity_observations":len(self.opportunity_observations),
            "unique_public_opportunity_ids":len(unique),"multi_route_memberships":multi_route,"company_filter_mismatches":self.company_filter_mismatches,
            "company_items_unverified":self.company_items_unverified,"national_opportunities_excluded":national,"procurement_like_excluded":excluded_procurement,
            "al_ahsa_accepted":len(accepted),"location_review_count":len(self.location_reviews),"sitemap_complete":sitemap_complete,
            "route_inventory":self.route_inventory,"unclassified_public_routes":sorted(set(unclassified)),"pagination_routes":sorted(pagination_urls),
            "load_more_controls":load_more,"page_errors":errors,"source_limitations":limitations,"parser_version":self.parser_version}
        return accepted,self.metrics["pages_requested"]


class MwanAdapter(BaseSourceAdapter):
    """Public MWAN opportunity pages; licensed companies and sector statistics are references only."""
    key="mwan"
    url="https://mwan.gov.sa/en/investment-opportunities"
    portal_url="https://mwared.mwan.gov.sa/en/investor/opportunities/cards"
    parser_version="2026.10.12-mwan-1"
    reference_terms=("licensed entities","licensed companies","الجهات المرخصة","المنشآت المرخصة","licensed and permitted")
    def __init__(self):self.metrics={};self.content_items=[];self.raw_candidates=[];self.location_reviews=[];self.diagnostics=[]

    async def _get(self,client,url):
        response=await client.get(url,headers={**self.headers,"Accept-Language":"en,ar;q=0.8"})
        if response.status_code in (401,403,429):raise SourceBlocked(f"MWAN public page access blocked (HTTP {response.status_code}): {url}")
        response.raise_for_status();return response

    @staticmethod
    def _labels(main):
        fields={}
        for row in main.select(".row, .field, .opportunity-item, li, tr"):
            text=re.sub(r"\s+"," ",row.get_text(" ",strip=True))
            m=re.match(r"([^:]{2,80})\s*:\s*(.+)$",text)
            if m:fields[m.group(1).strip()]=m.group(2).strip()
        return fields

    def _page_item(self,soup,url,source_family="PUBLIC_OPPORTUNITY"):
        main=soup.select_one("main") or soup.select_one("#wrapwrap") or soup.body or soup
        title_node=main.select_one("h1") or main.select_one("h2") or soup.title
        title=title_node.get_text(" ",strip=True) if title_node else ""
        text=re.sub(r"\s+"," ",main.get_text(" ",strip=True))
        pipeline_signal=bool(re.search(r"strategic capacity|sector strategy|future capacity|investment requirement|planned facility|planned project|متطلبات الاستثمار|الاستراتيجية",title+" "+text,re.I))
        if not title or (not pipeline_signal and not re.search(r"investment opportunity|فرصة استثمارية|opportunity",text,re.I)):return None
        fields=self._labels(main)
        location=next((v for k,v in fields.items() if re.search(r"location|city|الموقع|المدينة",k,re.I)),None)
        if not location:
            m=re.search(r"(?:Location|City|الموقع|المدينة)\s*[:\-]?\s*([\w\s\-،,]{2,100}?)(?=\s+(?:Value proposition|Scope|Markets|Value Chain|Expected|CAPEX|Project Duration|$))",text,re.I)
            location=m.group(1).strip(" ,،-") if m else None
        relevant,confidence,city,method=classify_location(location,title,text)
        links=[(a.get_text(" ",strip=True),urljoin(url,a.get("href",""))) for a in main.select("a[href]")]
        application=next((href for label,href in links if re.search(r"apply|submit|التقديم",label,re.I)),None)
        furas_link=next((href for _,href in links if "furas.momah.gov.sa" in href),None)
        slug=urlparse(url).path.rstrip("/").rsplit("/",1)[-1]
        official_id=next(((parse_qs(urlparse(href).query).get("type",[None])[0] or "furas")+":"+urlparse(href).path.rsplit("/",1)[-1] for _,href in links if "furas.momah.gov.sa" in href),None)
        awarded=bool(re.search(r"\bawarded\b|تمت الترسية|تم الترسية",title+" "+text,re.I))
        investor_solicitation=bool(re.search(r"apply|submit|register interest|investor|private sector partner|eoi|rfp|فرصة استثمارية|التقديم|المستثمر|القطاع الخاص",title+" "+text,re.I))
        pipeline=pipeline_signal and not investor_solicitation
        semantic="PIPELINE_REFERENCE" if pipeline else "INVESTMENT_OPPORTUNITY"
        if pipeline:relevant=False;confidence=0.0;method="strategic_reference_not_solicitation"
        external_id="mwan:"+(official_id or slug)
        # Aggregate sector statistics and broad investment promotion are not
        # item-level solicitations. Keep them as page evidence only.
        generic_sector=bool(re.search(r"sector (?:has|offers|offers over|investment opportunities)|investment opportunities worth|opportunities worth sar|\d[\d,.]*\s*(?:billion|bn)\s*(?:sar|riyals)",text,re.I))
        if generic_sector and not (furas_link or application):semantic="SECTOR_INFORMATION";relevant=False;confidence=0.0;method="aggregate_sector_information"
        return RawOpportunity(external_id=external_id,title=title,url=url,owner=None,
            location=location,status="AWARDED" if awarded else "ANNOUNCED",
            description=text[:6000],raw={"record_semantic_type":semantic,"source_family":source_family,"source_location":location,
                "project_stage":"AWARDED" if awarded else "PUBLIC_OPPORTUNITY","location_confidence_score":confidence,
                "location_detection_method":method,"location_evidence":" | ".join(x for x in (location,title) if x),
                "source_scope":"SOURCE_SCOPE_AL_AHSA" if relevant else None,"qualified":relevant,"official_furas_reference_url":furas_link,
                "application_url":application or furas_link,"qualification_reason":"Explicit Al-Ahsa evidence on a published MWAN investment opportunity page." if relevant else "Published project is retained as source-only evidence; no explicit Al-Ahsa locality is established." if not pipeline else "Strategic/pipeline reference has no specific solicitation.",
                "record_type":"PIPELINE_REFERENCE" if pipeline else "SPECIFIC_INVESTABLE_PROJECT","fields":fields,
                "official_source_id_original":official_id or slug})

    async def fetch(self,client):
        response=await self._get(client,self.url);soup=BeautifulSoup(response.text,"html.parser");main=soup.select_one("main") or soup.body or soup
        detail_urls=[]
        for a in main.select("a[href]"):
            href=urljoin(str(response.url),a.get("href",""));label=a.get_text(" ",strip=True)
            if re.search(r"more information|view details|مزيد من المعلومات|عرض التفاصيل",label,re.I):detail_urls.append(href)
        detail_urls=list(dict.fromkeys(detail_urls))
        # The investor cards route is an official public route linked from MWAN's
        # investor portal. It is queried without a session or account.
        portal=await self._get(client,self.portal_url);portal_soup=BeautifulSoup(portal.text,"html.parser")
        portal_urls=[]
        for a in (portal_soup.select_one("main") or portal_soup.body or portal_soup).select("a[href]"):
            href=urljoin(str(portal.url),a.get("href",""))
            if re.search(r"/investor/opportunity/\d+",urlparse(href).path):portal_urls.append(href)
        detail_urls=list(dict.fromkeys(detail_urls+portal_urls))
        rows=[];page_errors=[];source_pages=[(str(response.url),response.text,"PUBLIC_OPPORTUNITY_LIST"),(str(portal.url),portal.text,"PUBLIC_INVESTOR_CARDS")]
        for url in detail_urls:
            try:
                detail=await self._get(client,url);source_pages.append((str(detail.url),detail.text,"PUBLIC_OPPORTUNITY_DETAIL"))
                item=self._page_item(BeautifulSoup(detail.text,"html.parser"),str(detail.url),"INVESTOR_PORTAL" if "mwared.mwan.gov.sa" in str(detail.url) else "PUBLIC_OPPORTUNITY")
                if item:rows.append(item)
            except SourceBlocked:raise
            except httpx.HTTPError as exc:page_errors.append({"url":url,"error":str(exc)})
        # Keep the listing's overview content source-level only. Detail records have
        # URL- or cross-linked IDs, so distinct opportunities sharing a title stay distinct.
        unique={x.external_id:x for x in rows};rows=list(unique.values());accepted=[];pipeline_count=0;license_reference_excluded=0
        for raw in rows:
            if raw.raw.get("record_semantic_type")=="PIPELINE_REFERENCE":pipeline_count+=1;continue
            if raw.raw.get("record_semantic_type")=="SECTOR_INFORMATION":continue
            self.raw_candidates.append(raw)
            if (raw.raw or {}).get("location_confidence_score",0)>=LOCATION_ACCEPTANCE_THRESHOLD:accepted.append(raw)
            elif raw.raw.get("location_detection_method")=="province_only_not_qualified":
                self.location_reviews.append({"external_id":raw.external_id,"title":raw.title,"sector":"WASTE_SECTOR_INVESTMENT","location":raw.location,
                    "description":raw.description,"evidence":raw.location or "Eastern Province only","confidence_score":raw.raw.get("location_confidence_score",0.3),
                    "reason":"Specific MWAN investment opportunity identified, but Eastern Province alone does not establish Al-Ahsa relevance."})
        for url,text,kind in source_pages:
            doc=BeautifulSoup(text,"html.parser");root=doc.select_one("main") or doc.body or doc
            title=(root.select_one("h1") or doc.title);title=title.get_text(" ",strip=True) if title else kind
            raw_text=re.sub(r"\s+"," ",root.get_text(" ",strip=True))[:30000]
            attachments=[{"filename":a.get_text(" ",strip=True) or a.get("href"),"url":urljoin(url,a.get("href","")),"downloaded":False,"checksum":None}
                for a in root.select("a[href]") if re.search(r"\.(?:pdf|docx?|xlsx?)(?:\?|$)",a.get("href",""),re.I)]
            self.content_items.append({"url":url,"title":title,"publication_date":None,"content_type":kind,"raw_text":raw_text,
                "extracted_description":raw_text[:2500],"attachments":attachments,"detected_keywords":[],"parser_version":self.parser_version,
                "fingerprint":hashlib.sha256((text+json.dumps(attachments,ensure_ascii=False,sort_keys=True)).encode()).hexdigest()})
        complete=not page_errors and len(source_pages)==2+len(detail_urls) and bool(detail_urls)
        limitations=[]
        if not detail_urls:
            limitations.append({"limitation_type":"PUBLIC_DATA_PARTIAL","description":"The public MWAN investment listing exposed no opportunity detail links in this run; it cannot be interpreted as a complete zero inventory.","evidence_url":self.url,"resolution":"Retry the official public listing and its linked detail pages before using any zero count."})
        self.metrics={"technical_health":"HEALTHY" if complete else "WARNING","coverage_status":"COMPLETE_FOR_DEFINED_SCOPE" if complete else "PUBLIC_COVERAGE_LIMITED",
            "coverage_notes":"Monitor only specifically published MWAN investment projects. Licensed-company directories, sector statistics, and non-solicited strategy material are excluded from Master Opportunities.",
            "completeness_basis":"PUBLIC_COMPLETENESS","absolute_source_completeness":"UNKNOWN","public_scope_complete":complete,
            "source_collection_complete":complete,"reconciliation_safe":False,"pagination_complete":complete,
            "pages_requested":2+len(detail_urls),"pages_successful":len(source_pages),"records_received":len(rows),"records_parsed":len(rows),
            "unique_records":len(rows),"investment_pages_scanned":2+len(detail_urls),"specific_investment_opportunities":sum(1 for x in rows if x.raw.get("record_semantic_type")=="INVESTMENT_OPPORTUNITY"),
            "pipeline_references":pipeline_count,"licensed_company_reference_records_excluded":license_reference_excluded,
            "al_ahsa_accepted":len(accepted),"location_review_count":len(self.location_reviews),"page_errors":page_errors,
            "licensed_directory_excluded":True,"source_limitations":limitations,"parser_version":self.parser_version}
        return accepted,self.metrics["pages_requested"]


ADAPTERS = {"furas":FurasAdapter, "alahsa-opportunities":AlAhsaOpportunitiesAdapter,"ahda":AhdaAdapter,"invest-saudi":InvestSaudiAdapter,
    "kfu":KfuAdapter,"modon":ModonAdapter,"ncp":NcpAdapter,"nhc":NhcAdapter,"pif":PifPrivateSectorAdapter,"mwan":MwanAdapter}

def _opportunity_type_from_source(raw: RawOpportunity):
    payload=raw.raw or {}
    attributes=payload.get("attributes") or {}
    explicit=(payload.get("opportunity_type") or payload.get("opportunityType") or
              payload.get("record_semantic_type") or attributes.get("OPPORTUNITYTYPE"))
    if explicit:
        return str(explicit).strip()
    # These are explicit source enums, not activity labels.
    enum_types={"INVESTMENT_OPPORTUNITY","LEASE_OPPORTUNITY","COMMERCIAL_FACILITY_OPPORTUNITY","PPP_PROJECT","PPP_PROJECT_ANNOUNCEMENT","WASTE_SECTOR_INVESTMENT"}
    return raw.activity if raw.activity in enum_types else None

def normalized_record(raw: RawOpportunity) -> dict:
    location_raw=raw.raw or {}
    if raw.location_source_filtered and location_raw.get("source_scope")=="SOURCE_SCOPE_AL_AHSA":
        scope_method=location_raw.get("location_detection_method")
        explicit_site=scope_method in {"OFFICIAL_CAMPUS_SCOPE","EXPLICIT_CITY_LIST"}
        relevant,confidence,city,method=True,1.0,"الأحساء" if explicit_site else "",scope_method or "SOURCE_SCOPE"
        evidence=location_raw.get("location_evidence") or ("AHDA institutional scope; no city or district inferred from the publisher scope." if not explicit_site else "Official project content explicitly identifies an Al-Ahsa campus or city.")
    elif location_raw.get("location_confidence_score") is not None:
        confidence=float(location_raw["location_confidence_score"])
        relevant=confidence>=LOCATION_ACCEPTANCE_THRESHOLD
        method=location_raw.get("location_detection_method","")
        evidence=location_raw.get("location_evidence","")
        city="الأحساء" if relevant else ""
    elif raw.location_source_filtered:
        relevant,confidence,city,method=True,1.0,"الأحساء","SOURCE_FILTER"
        city_id=(raw.raw or {}).get("attributes",{}).get("CITY_ID")
        evidence=("Furas CITY_ID filter"+(f"={city_id}" if city_id is not None else "")
                  if city_id is not None else "Al-Ahsa-only public platform")
        evidence += " | "+" | ".join(x for x in (raw.location,raw.title) if x)
    else:
        relevant, confidence, city, method = classify_location(raw.location, raw.title, raw.description)
        evidence=" | ".join(x for x in (raw.location,raw.title) if x)
    area = parse_number(raw.area_text)
    contract = parse_number(raw.contract_text)
    from .standardization import canonical_identity
    taxonomy=location_raw.get("source_taxonomy") or {}
    normalized_taxonomy=location_raw.get("normalized_taxonomy") or {}
    explicit_sector=taxonomy.get("sector")
    normalized_sector=normalize_sector(normalized_taxonomy.get("sector")) if normalized_taxonomy.get("sector") else None
    if explicit_sector:
        sector=normalize_sector(explicit_sector)
    elif normalized_sector:
        sector=normalized_sector
    else:
        identity=canonical_identity("sector",raw.activity)
        sector=identity["label"] if identity and identity["id"] != "sector:unspecified" else None
    opportunity_type = _opportunity_type_from_source(raw)
    investment_model = location_raw.get("investment_model")
    return {
        "relevant":relevant,"location_confidence_score":confidence,"city":city if method=="SOURCE_SCOPE" else city or "الأحساء",
        "location_detection_method":method,"location_evidence":evidence,
        "title_ar":raw.title,"normalized_title":normalize_arabic(raw.title),"reference_number":raw.reference,
        "opportunity_owner":raw.owner,"sector":sector,"activity":raw.activity,"sub_activity":raw.sub_activity,"subsector":(location_raw.get("normalized_taxonomy") or {}).get("subsector"),"opportunity_type":opportunity_type,"investment_model":investment_model,
        "district":None,"location_description":raw.location,"land_area_sqm":area,
        "latitude":raw.latitude,"longitude":raw.longitude,"publication_date":(raw.raw or {}).get("publication_date"),
        "contract_duration_years":contract,"submission_deadline":raw.deadline,"status":raw.status or "غير محددة",
        "short_description":raw.description,"full_description":raw.description,"data_quality_score":0.75,
    }
