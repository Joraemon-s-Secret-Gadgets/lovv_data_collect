import json
import os

from dynamodb_search import SearchInputError, build_repository, collect_columns, collect_indexes, query_index_items, search_items, to_jsonable


def lambda_handler(event, context):
    method = _method(event)
    path = _path(event)
    headers = event.get("headers") or {}
    origin = headers.get("origin") or headers.get("Origin")

    if method == "OPTIONS":
        return _response(204, {}, origin)

    auth_error = _auth_error(headers)
    if auth_error:
        return _response(401, {"message": auth_error, "authMode": "required"}, origin)

    try:
        repository = build_repository()
        params = event.get("queryStringParameters") or {}
        if path.endswith("/api/columns"):
            body = collect_columns(repository, params)
            body["authMode"] = _auth_mode()
            return _response(200, body, origin)
        if path.endswith("/api/indexes"):
            body = collect_indexes(repository)
            body["authMode"] = _auth_mode()
            return _response(200, body, origin)
        if path.endswith("/api/search"):
            body = search_items(repository, params)
            body["authMode"] = _auth_mode()
            return _response(200, body, origin)
        if path.endswith("/api/query-index"):
            body = query_index_items(repository, params)
            body["authMode"] = _auth_mode()
            return _response(200, body, origin)
        return _response(404, {"message": "요청한 API를 찾을 수 없습니다."}, origin)
    except SearchInputError as error:
        return _response(400, {"message": str(error)}, origin)
    except Exception:
        return _response(500, {"message": "DynamoDB 조회 요청에 실패했습니다."}, origin)


def _method(event):
    return (
        ((event.get("requestContext") or {}).get("http") or {}).get("method")
        or event.get("httpMethod")
        or "GET"
    ).upper()


def _path(event):
    return event.get("rawPath") or event.get("path") or ""


def _auth_error(headers):
    expected = os.environ.get("VIEWER_ACCESS_TOKEN", "").strip()
    if not expected:
        return None

    authorization = headers.get("authorization") or headers.get("Authorization") or ""
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return "API 토큰이 필요합니다."
    if authorization[len(prefix) :].strip() != expected:
        return "API 토큰이 올바르지 않습니다."
    return None


def _auth_mode():
    return "required" if os.environ.get("VIEWER_ACCESS_TOKEN", "").strip() else "disabled"


def _response(status_code, body, origin=None):
    return {
        "statusCode": status_code,
        "headers": _headers(origin),
        "body": json.dumps(to_jsonable(body), ensure_ascii=False),
    }


def _headers(origin=None):
    allowed = [
        item.strip()
        for item in os.environ.get(
            "ALLOWED_CORS_ORIGIN",
            "http://127.0.0.1:8787,http://localhost:8787",
        ).split(",")
        if item.strip()
    ]
    if "*" in allowed:
        allow_origin = "*"
    elif origin and origin in allowed:
        allow_origin = origin
    elif allowed:
        allow_origin = allowed[0]
    else:
        allow_origin = "http://127.0.0.1:8787"

    return {
        "Content-Type": "application/json; charset=utf-8",
        "Access-Control-Allow-Origin": allow_origin,
        "Access-Control-Allow-Headers": "Authorization,Content-Type",
        "Access-Control-Allow-Methods": "GET,OPTIONS",
        "Vary": "Origin",
    }
