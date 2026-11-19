import sys,yaml
d=yaml.safe_load(open('data_gated_reviews.yaml')); items=d['reviews'] if isinstance(d,dict) else d
v=[x for x in items if x.get('review_id')==sys.argv[1]][0]
print("SET default_transaction_read_only = on;\n"+v['predicate_sql'].rstrip().rstrip(';')+";")
