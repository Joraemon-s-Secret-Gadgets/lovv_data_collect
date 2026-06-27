import boto3
from collections import defaultdict

session = boto3.Session(profile_name="skn26_final", region_name="us-east-1")
ddb = session.resource("dynamodb")
table = ddb.Table("TourKoreaDomainData")

# Full scan to understand province_key distribution
province_counts = defaultdict(int)
sample_none = []
scan_kwargs = {}

while True:
    resp = table.scan(**scan_kwargs)
    for item in resp.get("Items", []):
        pk = item.get("province_key", "(NO_ATTR)")
        province_counts[pk] += 1
        if pk == "(NO_ATTR)" and len(sample_none) < 3:
            sample_none.append({k: v for k, v in item.items() if k in ("PK", "SK", "city_key", "province", "city_name_ko", "entity_type")})
    if "LastEvaluatedKey" in resp:
        scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    else:
        break

print(f"Total province_key distribution:")
for pk, count in sorted(province_counts.items(), key=lambda x: -x[1]):
    print(f"  {pk}: {count}")

if sample_none:
    print(f"\nSample items without province_key attr:")
    for s in sample_none:
        print(f"  {s}")
