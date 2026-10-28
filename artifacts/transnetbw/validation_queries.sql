-- =====================================================================
-- IRIS-SIG-30 · TransnetBW Project Radar — validation queries
--
-- Run against the staging database after a harvest:
--     psql "$TRANSNETBW_DATABASE_URL" -f artifacts/transnetbw/validation_queries.sql
--
-- Each query is labelled [Vn]. "expect: 0 rows" queries are invariants:
-- any row returned is a defect (tests/test_transnetbw_report.py runs every
-- one of them against a harvested database). "expect: review" queries are
-- for reading.
-- =====================================================================


-- [V1] Duplicate natural keys — expect: 0 rows
select source_system, source_record_id, count(*) as copies
from iris_staging.signal_ingest
group by source_system, source_record_id
having count(*) > 1;


-- [V2] Geometry that is not a valid EPSG:25832 point — expect: 0 rows
select source_record_id, ST_SRID(geom) as srid, GeometryType(geom) as type
from iris_staging.signal_ingest
where geom is not null
  and (ST_SRID(geom) <> 25832 or GeometryType(geom) <> 'POINT' or not ST_IsValid(geom));


-- [V3] Points outside the record's reference region (Baden-Württemberg) — expect: 0 rows
select s.source_record_id, ST_AsText(s.geom) as point
from iris_staging.signal_ingest s
join iris_staging.ref_region r on r.region_code = s.region_code
where s.geom is not null
  and not ST_Within(s.geom, r.geom);


-- [V4] "Resolved" without a point, or a point without "resolved" — expect: 0 rows
select source_record_id, location_status, geom is not null as has_point
from iris_staging.signal_ingest
where (location_status = 'resolved') <> (geom is not null);


-- [V5] Records that cannot be traced to their source or their run — expect: 0 rows
select s.source_record_id
from iris_staging.signal_ingest s
left join iris_staging.ingest_run first_run on first_run.run_id = s.first_seen_run_id
left join iris_staging.ingest_run last_run on last_run.run_id = s.last_seen_run_id
where s.source_url not like 'https://www.transnetbw.de/%'
   or first_run.run_id is null
   or last_run.run_id is null
   or s.content_hash !~ '^[0-9a-f]{64}$';


-- [V6] Press releases with an implausible publication date — expect: 0 rows
select source_record_id, published_at
from iris_staging.signal_ingest
where record_kind = 'press_release'
  and (published_at > current_date or published_at < date '2000-01-01');


-- [V7] Personal contact data (e-mail addresses, phone numbers) in staged text — expect: 0 rows
select source_record_id
from iris_staging.signal_ingest
where concat_ws(' ', title, summary, attributes::text) ~ '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}'
   or concat_ws(' ', title, summary, attributes::text) ~ '\+49[ /]?[0-9]';


-- [V8] Version history out of step with the current row — expect: 0 rows
select s.source_record_id
from iris_staging.signal_ingest s
where not exists (
    select 1 from iris_staging.signal_ingest_version v
    where v.signal_id = s.id and v.content_hash = s.content_hash
);


-- [V9] Records by kind, signal type and stage — expect: review
select record_kind, signal_type, project_stage, count(*) as records
from iris_staging.signal_ingest
where retired_at is null
group by record_kind, signal_type, project_stage
order by record_kind, signal_type, project_stage;


-- [V10] Locations that are not a single point, with the reason — expect: review
select source_record_id, location_status, location_text,
       attributes ->> 'location_note' as note,
       jsonb_array_length(coalesce(attributes -> 'endpoints', '[]'::jsonb)) as endpoints
from iris_staging.signal_ingest
where location_status <> 'resolved'
order by location_status, source_record_id;


-- [V11] Press releases whose date is not confirmed by both article and feed — expect: review
select source_record_id, published_at,
       attributes ->> 'article_date' as article_date,
       attributes ->> 'feed_date' as feed_date,
       quality_flags
from iris_staging.signal_ingest
where record_kind = 'press_release' and not published_at_verified;


-- [V12] Review queue — expect: review
select source_record_id, signal_type, attributes -> 'review_reasons' as reasons
from iris_staging.signal_ingest
where review_status = 'needs_review'
order by source_record_id;


-- [V13] Press releases linked to a project that is not staged — expect: review
-- (0 rows after a full live harvest; offline runs cover 8 of 25 projects)
select p.source_record_id, p.attributes ->> 'related_project' as related_project
from iris_staging.signal_ingest p
left join iris_staging.signal_ingest project
       on project.source_system = p.source_system
      and project.source_record_id = p.attributes ->> 'related_project'
where p.record_kind = 'press_release'
  and p.attributes ? 'related_project'
  and project.id is null;


-- [V14] Records with more than one content version — expect: review
select s.source_record_id, count(v.id) as versions, min(v.created_at) as first_version, max(v.created_at) as last_version
from iris_staging.signal_ingest s
join iris_staging.signal_ingest_version v on v.signal_id = s.id
group by s.source_record_id
having count(v.id) > 1;


-- [V15] Retired records — expect: review
select source_record_id, missing_run_count, retired_at
from iris_staging.signal_ingest
where retired_at is not null;


-- [V16] The last ten runs — expect: review
select run_id, mode, status, exit_code, started_at, finished_at,
       stats -> 'load' as load, stats -> 'issues' -> 'by_code' as issues
from iris_staging.ingest_run
order by started_at desc
limit 10;


-- [V17] Issues of the most recent run, by severity and code — expect: review
select i.severity, i.code, count(*) as issues
from iris_staging.ingest_issue i
where i.run_id = (select run_id from iris_staging.ingest_run order by started_at desc limit 1)
group by i.severity, i.code
order by i.severity, issues desc;
