import base64
import json
import os
from decimal import Decimal


DEFAULT_TABLE_NAME = "TourKoreaDomainData"
DEFAULT_LIMIT = 25
MAX_LIMIT = 100
DEFAULT_SAMPLE_SIZE = 50
MAX_SAMPLE_SIZE = 200
DEFAULT_SCAN_PAGE_SIZE = 100
MAX_SCAN_PAGE_SIZE = 500
DEFAULT_MAX_SCAN_PAGES = 4
MAX_QUERY_LENGTH = 200


class SearchInputError(ValueError):
    pass


class JsonFileRepository:
    def __init__(self, path):
        self.path = _resolve_path(path)

    def scan(self, limit, exclusive_start_key=None):
        with open(self.path, "r", encoding="utf-8") as file:
            items = json.load(file)

        offset = 0
        if exclusive_start_key:
            offset = int(exclusive_start_key.get("offset", 0))

        page = items[offset : offset + limit]
        next_offset = offset + len(page)
        next_key = {"offset": next_offset} if next_offset < len(items) else None
        return {
            "Items": page,
            "Count": len(page),
            "ScannedCount": len(page),
            "LastEvaluatedKey": next_key,
        }

    def describe_indexes(self):
        return [
            {
                "indexName": "GSI1",
                "keySchema": [
                    {"attributeName": "city_key", "keyType": "HASH"},
                    {"attributeName": "domain_sort_key", "keyType": "RANGE"},
                ],
                "projectionType": "ALL",
            },
            {
                "indexName": "GSI2",
                "keySchema": [
                    {"attributeName": "province_key", "keyType": "HASH"},
                    {"attributeName": "domain_sort_key", "keyType": "RANGE"},
                ],
                "projectionType": "ALL",
            },
            {
                "indexName": "GSI3",
                "keySchema": [
                    {"attributeName": "entity_type", "keyType": "HASH"},
                    {"attributeName": "domain_sort_key", "keyType": "RANGE"},
                ],
                "projectionType": "ALL",
            },
        ]

    def query_index(self, index_name, partition_key, partition_value, sort_key=None, sort_mode="", sort_value="", sort_value_to="", limit=DEFAULT_LIMIT, exclusive_start_key=None):
        with open(self.path, "r", encoding="utf-8") as file:
            items = json.load(file)

        offset = 0
        if exclusive_start_key:
            offset = int(exclusive_start_key.get("offset", 0))

        matched = []
        for item in items:
            if str(item.get(partition_key, "")) != str(partition_value):
                continue
            if sort_key and sort_mode and sort_value and not _sort_condition_matches(item.get(sort_key), sort_mode, sort_value, sort_value_to):
                continue
            matched.append(item)

        page = matched[offset : offset + limit]
        next_offset = offset + len(page)
        next_key = {"offset": next_offset} if next_offset < len(matched) else None
        return {
            "Items": page,
            "Count": len(page),
            "ScannedCount": len(page),
            "LastEvaluatedKey": next_key,
        }


class DynamoDbRepository:
    def __init__(self, table_name=None, region_name=None, dynamodb_resource=None):
        self.table_name = table_name or os.environ.get("DYNAMODB_TABLE_NAME") or DEFAULT_TABLE_NAME
        if dynamodb_resource is None:
            dynamodb_resource = _dynamodb_resource(region_name)
        self.client = dynamodb_resource.meta.client
        self.table = dynamodb_resource.Table(self.table_name)

    def scan(self, limit, exclusive_start_key=None):
        kwargs = {"Limit": limit}
        if exclusive_start_key:
            kwargs["ExclusiveStartKey"] = exclusive_start_key
        return self.table.scan(**kwargs)

    def describe_indexes(self):
        response = self.client.describe_table(TableName=self.table_name)
        indexes = response.get("Table", {}).get("GlobalSecondaryIndexes", []) or []
        return [
            {
                "indexName": index["IndexName"],
                "keySchema": [
                    {
                        "attributeName": key["AttributeName"],
                        "keyType": key["KeyType"],
                    }
                    for key in index.get("KeySchema", [])
                ],
                "projectionType": index.get("Projection", {}).get("ProjectionType", ""),
            }
            for index in indexes
        ]

    def query_index(self, index_name, partition_key, partition_value, sort_key=None, sort_mode="", sort_value="", sort_value_to="", limit=DEFAULT_LIMIT, exclusive_start_key=None):
        try:
            from boto3.dynamodb.conditions import Key
        except ImportError as error:
            raise RuntimeError("실제 DynamoDB GSI 조회에는 boto3가 필요합니다.") from error

        expression = Key(partition_key).eq(_parse_attribute_value(partition_value))
        if sort_key and sort_mode and sort_value:
            expression = expression & _build_sort_expression(Key(sort_key), sort_mode, sort_value, sort_value_to)

        kwargs = {
            "IndexName": index_name,
            "KeyConditionExpression": expression,
            "Limit": limit,
        }
        if exclusive_start_key:
            kwargs["ExclusiveStartKey"] = exclusive_start_key
        return self.table.query(**kwargs)


def search_items(repository, query_params=None, env=None):
    env = env or os.environ
    params = query_params or {}
    table_name = env.get("DYNAMODB_TABLE_NAME") or DEFAULT_TABLE_NAME
    keyword = _bounded_text(params.get("q", ""), MAX_QUERY_LENGTH)
    column = _clean_column(params.get("column"))
    mode = params.get("mode", "contains")
    if mode not in ("contains", "equals"):
        raise SearchInputError("검색 방식은 포함 또는 정확히 일치만 사용할 수 있습니다.")

    limit = _bounded_int(params.get("limit"), DEFAULT_LIMIT, 1, MAX_LIMIT)
    page_size = _bounded_int(
        env.get("SCAN_PAGE_SIZE"),
        DEFAULT_SCAN_PAGE_SIZE,
        1,
        MAX_SCAN_PAGE_SIZE,
    )
    max_pages = _bounded_int(
        env.get("MAX_SCAN_PAGES"),
        DEFAULT_MAX_SCAN_PAGES,
        1,
        20,
    )
    cursor_key = decode_cursor(params.get("cursor"))

    matches = []
    scanned_count = 0
    searched_pages = 0
    last_key = cursor_key
    columns = set()

    while searched_pages < max_pages and len(matches) < limit:
        request_limit = min(page_size, limit - len(matches))
        response = repository.scan(limit=request_limit, exclusive_start_key=last_key)
        searched_pages += 1
        items = response.get("Items", [])
        scanned_count += int(response.get("ScannedCount", len(items)))

        for item in items:
            columns.update(item.keys())
            if _item_matches(item, keyword, column, mode):
                matches.append(to_jsonable(item))
                if len(matches) >= limit:
                    break

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break

    result_columns = sorted(columns.union(extract_columns(matches)), key=str.lower)
    return {
        "tableName": table_name,
        "items": matches,
        "columns": result_columns,
        "count": len(matches),
        "scannedCount": scanned_count,
        "nextCursor": encode_cursor(last_key),
        "searchedPages": searched_pages,
        "scanLimitReached": bool(last_key and searched_pages >= max_pages),
    }


def collect_columns(repository, query_params=None, env=None):
    env = env or os.environ
    params = query_params or {}
    table_name = env.get("DYNAMODB_TABLE_NAME") or DEFAULT_TABLE_NAME
    sample_size = _bounded_int(params.get("sampleSize"), DEFAULT_SAMPLE_SIZE, 1, MAX_SAMPLE_SIZE)
    response = repository.scan(limit=sample_size)
    items = [to_jsonable(item) for item in response.get("Items", [])]
    return {
        "tableName": table_name,
        "columns": extract_columns(items),
        "sampleSize": sample_size,
        "scannedCount": int(response.get("ScannedCount", len(items))),
    }


def collect_indexes(repository, env=None):
    env = env or os.environ
    return {
        "tableName": env.get("DYNAMODB_TABLE_NAME") or DEFAULT_TABLE_NAME,
        "indexes": repository.describe_indexes(),
    }


def query_index_items(repository, query_params=None, env=None):
    env = env or os.environ
    params = query_params or {}
    table_name = env.get("DYNAMODB_TABLE_NAME") or DEFAULT_TABLE_NAME
    indexes = repository.describe_indexes()
    index_name = _bounded_text(params.get("indexName", ""), 128)
    if not index_name:
        raise SearchInputError("GSI 인덱스를 선택해야 합니다.")

    index = _find_index(indexes, index_name)
    if not index:
        raise SearchInputError("선택한 GSI 인덱스를 찾을 수 없습니다.")

    partition_key = _index_key(index, "HASH")
    sort_key = _index_key(index, "RANGE")
    partition_value = _bounded_text(params.get("partitionValue", ""), MAX_QUERY_LENGTH)
    if not partition_value:
        raise SearchInputError(f"{partition_key} 파티션 키 값을 입력해야 합니다.")

    sort_mode = params.get("sortMode", "")
    if sort_mode not in ("", "equals", "begins_with", "between", "gt", "gte", "lt", "lte"):
        raise SearchInputError("정렬 키 조건이 올바르지 않습니다.")
    sort_value = _bounded_text(params.get("sortValue", ""), MAX_QUERY_LENGTH)
    sort_value_to = _bounded_text(params.get("sortValueTo", ""), MAX_QUERY_LENGTH)
    if sort_mode and not sort_key:
        raise SearchInputError("이 GSI에는 정렬 키가 없습니다.")
    if sort_mode and not sort_value:
        raise SearchInputError("정렬 키 값을 입력해야 합니다.")
    if sort_mode == "between" and not sort_value_to:
        raise SearchInputError("범위 조회에는 끝 값을 입력해야 합니다.")

    limit = _bounded_int(params.get("limit"), DEFAULT_LIMIT, 1, MAX_LIMIT)
    cursor_key = decode_cursor(params.get("cursor"))
    response = repository.query_index(
        index_name=index_name,
        partition_key=partition_key,
        partition_value=partition_value,
        sort_key=sort_key,
        sort_mode=sort_mode,
        sort_value=sort_value,
        sort_value_to=sort_value_to,
        limit=limit,
        exclusive_start_key=cursor_key,
    )
    items = [to_jsonable(item) for item in response.get("Items", [])]
    return {
        "tableName": table_name,
        "indexName": index_name,
        "keySchema": index.get("keySchema", []),
        "items": items,
        "columns": extract_columns(items),
        "count": len(items),
        "scannedCount": int(response.get("ScannedCount", len(items))),
        "nextCursor": encode_cursor(response.get("LastEvaluatedKey")),
        "queryType": "gsi",
    }


def extract_columns(items):
    columns = set()
    for item in items:
        if isinstance(item, dict):
            columns.update(item.keys())
    return sorted(columns, key=str.lower)


def encode_cursor(key):
    if not key:
        return None
    raw = json.dumps(to_jsonable(key), ensure_ascii=False, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(cursor):
    if not cursor:
        return None
    try:
        padded = cursor + ("=" * (-len(cursor) % 4))
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        value = json.loads(raw)
    except (ValueError, TypeError) as error:
        raise SearchInputError("커서 값이 올바르지 않습니다.") from error
    if not isinstance(value, dict):
        raise SearchInputError("커서 값이 올바르지 않습니다.")
    return value


def to_jsonable(value):
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(item_value) for key, item_value in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item_value) for item_value in value]
    if isinstance(value, tuple):
        return [to_jsonable(item_value) for item_value in value]
    if isinstance(value, set):
        return sorted(to_jsonable(item_value) for item_value in value)
    return value


def build_repository(env=None):
    env = env or os.environ
    mock_path = env.get("MOCK_DATA_PATH")
    if mock_path:
        return JsonFileRepository(mock_path)
    return DynamoDbRepository(
        table_name=env.get("DYNAMODB_TABLE_NAME") or DEFAULT_TABLE_NAME,
        region_name=env.get("AWS_REGION"),
    )


def _item_matches(item, keyword, column, mode):
    if not keyword:
        return True

    if column:
        values = [_value_at_path(item, column)]
    else:
        values = list(item.values())

    keyword_folded = keyword.casefold()
    for value in values:
        if value is None:
            continue
        text = _search_text(value)
        text_folded = text.casefold()
        if mode == "equals" and text_folded == keyword_folded:
            return True
        if mode == "contains" and keyword_folded in text_folded:
            return True
    return False


def _value_at_path(item, path):
    current = item
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _search_text(value):
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(to_jsonable(value), ensure_ascii=False, sort_keys=True)
    return str(to_jsonable(value))


def _find_index(indexes, index_name):
    for index in indexes:
        if index.get("indexName") == index_name:
            return index
    return None


def _index_key(index, key_type):
    for key in index.get("keySchema", []):
        if key.get("keyType") == key_type:
            return key.get("attributeName")
    return ""


def _sort_condition_matches(value, sort_mode, sort_value, sort_value_to=""):
    if value is None:
        return False
    text = str(value)
    if sort_mode == "equals":
        return text == str(sort_value)
    if sort_mode == "begins_with":
        return text.startswith(str(sort_value))
    if sort_mode == "between":
        return str(sort_value) <= text <= str(sort_value_to)
    if sort_mode == "gt":
        return text > str(sort_value)
    if sort_mode == "gte":
        return text >= str(sort_value)
    if sort_mode == "lt":
        return text < str(sort_value)
    if sort_mode == "lte":
        return text <= str(sort_value)
    return True


def _build_sort_expression(key, sort_mode, sort_value, sort_value_to=""):
    value = _parse_attribute_value(sort_value)
    if sort_mode == "equals":
        return key.eq(value)
    if sort_mode == "begins_with":
        return key.begins_with(str(sort_value))
    if sort_mode == "between":
        return key.between(value, _parse_attribute_value(sort_value_to))
    if sort_mode == "gt":
        return key.gt(value)
    if sort_mode == "gte":
        return key.gte(value)
    if sort_mode == "lt":
        return key.lt(value)
    if sort_mode == "lte":
        return key.lte(value)
    raise SearchInputError("정렬 키 조건이 올바르지 않습니다.")


def _parse_attribute_value(value):
    text = str(value)
    if text.startswith("json:"):
        try:
            return json.loads(text[5:])
        except ValueError as error:
            raise SearchInputError("json: 형식의 키 값이 올바르지 않습니다.") from error
    return text


def _clean_column(column):
    if column is None:
        return ""
    column = str(column).strip()
    if len(column) > 120:
        raise SearchInputError("컬럼명이 너무 깁니다.")
    return column


def _bounded_text(value, max_length):
    text = str(value or "").strip()
    if len(text) > max_length:
        raise SearchInputError("검색어가 너무 깁니다.")
    return text


def _bounded_int(value, default, minimum, maximum):
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise SearchInputError("숫자 입력값이 올바르지 않습니다.") from error
    return max(minimum, min(number, maximum))


def _resolve_path(path):
    if os.path.isabs(path):
        return path
    if os.path.exists(path):
        return path
    backend_dir = os.path.dirname(__file__)
    candidate = os.path.join(os.path.dirname(backend_dir), path)
    if os.path.exists(candidate):
        return candidate
    return os.path.join(backend_dir, path)


def _dynamodb_resource(region_name=None):
    try:
        import boto3
    except ImportError as error:
        raise RuntimeError("실제 DynamoDB 조회에는 boto3가 필요합니다.") from error
    kwargs = {}
    if region_name:
        kwargs["region_name"] = region_name
    return boto3.resource("dynamodb", **kwargs)
