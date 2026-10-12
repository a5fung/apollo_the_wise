#!/bin/bash
cd /Users/alvinfung/apollo_the_wise/scripts/probes/_verify_1012/210
for i in $(seq 1 40); do
  n=$(ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -At -c \"select count(*) from mi_job_runs where job_id='tv_news_shadow' and started_at >= '2026-10-12 00:00-04'\"" 2>/dev/null)
  if [ "$n" != "" ] && [ "$n" != "0" ]; then break; fi
  sleep 30
done
sleep 20
ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F \$'\\t'" < q4.sql > q4.out 2>&1
TZ=America/New_York date > q4.pulled_at
echo done
