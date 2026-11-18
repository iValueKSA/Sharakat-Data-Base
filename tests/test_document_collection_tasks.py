from app.celery_app import celery_app
from app.document_collection.config import feature_flags
from app.document_collection.tasks import (_retry_if_needed, collect_allowlisted_batch,
    collect_source_opportunity, refresh_candidate, retry_verification, summarize_run_task)


def test_tasks_are_registered_explicitly_but_disabled_and_unscheduled_by_default(monkeypatch):
    for name in ("ENGINE", "MANUAL", "SCHEDULED", "STAGING", "AUTO_APPROVAL", "AUTO_PUBLICATION"):
        monkeypatch.delenv(f"DOCUMENT_COLLECTION_{name}_ENABLED", raising=False)
    flags=feature_flags()
    assert flags.manual_tasks_allowed() is False
    assert flags.scheduled_collection is False
    assert flags.automatic_approval is False and flags.automatic_publication is False
    assert collect_source_opportunity.run(3188)["status"]=="DISABLED"
    assert collect_allowlisted_batch.run([3188])["status"]=="DISABLED"
    assert refresh_candidate.run(1)["status"]=="DISABLED"
    assert retry_verification.run(1)["status"]=="DISABLED"
    assert summarize_run_task.run(1)["status"]=="DISABLED"
    assert not any("document_collection" in entry.get("task","") for entry in celery_app.conf.beat_schedule.values())
    assert celery_app.conf.task_routes[collect_source_opportunity.name]["queue"]=="document_collection"


def test_batch_task_rejects_unbounded_requests_even_if_flag_enabled(monkeypatch):
    monkeypatch.setenv("DOCUMENT_COLLECTION_ENGINE_ENABLED","true")
    monkeypatch.setenv("DOCUMENT_COLLECTION_MANUAL_ENABLED","true")
    monkeypatch.setenv("DOCUMENT_COLLECTION_STAGING_ENABLED","true")
    result=collect_allowlisted_batch.run(list(range(1,27)))
    assert result["status"]=="REJECTED"


def test_retry_preserves_task_arguments_and_resumable_run_id():
    from unittest.mock import patch

    class RetrySignal(Exception):
        def __init__(self,args,countdown):
            self.retry_args=args;self.countdown=countdown
    class Task:
        max_retries=3
        class Request:retries=0
        request=Request()
        def retry(self,*,args,countdown):raise RetrySignal(args,countdown)
    result={"run_id":17,"failures":[{"status":"TEMPORARY_FAILURE"}]}
    for original,expected in [([3188,None],[3188,17]),([[3188,3190],None],[[3188,3190],17]),([42,None],[42,17])]:
        try:
            with patch("app.document_collection.tasks.random.uniform", return_value=0):
                _retry_if_needed(Task(),result,original)
        except RetrySignal as exc:
            assert exc.retry_args==expected and exc.countdown==30
        else:
            raise AssertionError("Retryable source failure must be rescheduled with the same task contract")
    result["failures"][0]["error_evidence"]={"retry_after_seconds":120}
    try:
        with patch("app.document_collection.tasks.random.uniform", return_value=0):
            _retry_if_needed(Task(),result,[3188,None])
    except RetrySignal as exc:
        assert exc.countdown==120
    else:
        raise AssertionError("Retry-After must be honored within the configured maximum")
