"""PostgreSQL logical backups with checksums and tiered local retention."""
from __future__ import annotations
import hashlib, json, os, subprocess, uuid
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.engine import make_url


def backup_postgres() -> dict:
    database_url=os.getenv("DATABASE_URL","")
    if not database_url.startswith(("postgresql://","postgresql+psycopg://")):
        raise RuntimeError("PostgreSQL backup requires a PostgreSQL DATABASE_URL")
    url=make_url(database_url)
    directory=Path(os.getenv("BACKUP_DIR","/backups"));directory.mkdir(parents=True,exist_ok=True)
    started=datetime.now(timezone.utc);backup_id=started.strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:8]
    output=directory/f"{backup_id}.dump";metadata=directory/f"{backup_id}.json"
    env=os.environ.copy()
    if url.password is not None:env["PGPASSWORD"]=url.password
    args=["pg_dump","--format=custom","--no-owner","--no-acl","--host",url.host or "localhost","--port",str(url.port or 5432),"--username",url.username or "postgres","--dbname",url.database or "postgres","--file",str(output)]
    try:
        subprocess.run(args,env=env,check=True,timeout=int(os.getenv("BACKUP_TIMEOUT_SECONDS","7200")),capture_output=True,text=True)
        digest=hashlib.sha256(output.read_bytes()).hexdigest();completed=datetime.now(timezone.utc)
        record={"backup_id":backup_id,"started_at":started.isoformat(),"completed_at":completed.isoformat(),"size_bytes":output.stat().st_size,"status":"SUCCESS","storage_location":str(output),"sha256":digest}
        metadata.write_text(json.dumps(record,indent=2),encoding="utf-8")
        apply_retention(directory)
        return record
    except Exception:
        output.unlink(missing_ok=True);metadata.unlink(missing_ok=True)
        raise


def apply_retention(directory: Path) -> None:
    """Retain the newest configured daily, weekly, and monthly restore points."""
    daily=int(os.getenv("BACKUP_RETAIN_DAILY","7"));weekly=int(os.getenv("BACKUP_RETAIN_WEEKLY","4"));monthly=int(os.getenv("BACKUP_RETAIN_MONTHLY","3"))
    files=sorted(directory.glob("*.dump"),reverse=True);keep=set()
    for path in files[:daily]:keep.add(path.name)
    seen_weeks=set();seen_months=set()
    for path in files:
        stamp=path.name[:16]
        try:day=datetime.strptime(stamp,"%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:continue
        week=day.isocalendar()[:2];month=(day.year,day.month)
        if week not in seen_weeks and len(seen_weeks)<weekly:keep.add(path.name);seen_weeks.add(week)
        if month not in seen_months and len(seen_months)<monthly:keep.add(path.name);seen_months.add(month)
    for path in files:
        if path.name not in keep:
            path.unlink(missing_ok=True);path.with_suffix(".json").unlink(missing_ok=True)
