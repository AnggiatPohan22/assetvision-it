from app.main import app


def test_openapi_security_csrf_pagination_and_binary_contract(client):
    schema = client.get("/openapi.json").json()
    assert schema == app.openapi()
    cookie = schema["components"]["securitySchemes"]["SessionCookie"]
    assert cookie["type"] == "apiKey" and cookie["in"] == "cookie" and cookie["name"] == "av_access"
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            if method not in {"get", "post", "patch", "delete"}:
                continue
            public = path in {
                "/api/v1/health",
                "/api/v1/ready",
                "/api/v1/auth/csrf",
                "/api/v1/auth/login",
            }
            assert bool(operation.get("security")) is not public
            if method != "get":
                headers = {
                    p["name"]
                    for p in operation["parameters"]
                    if p["in"] == "header" and p["required"]
                }
                assert {"Origin", "X-CSRF-Token"} <= headers
    models = schema["paths"]["/api/v1/device-models"]["get"]
    parameters = {p["name"]: p["schema"] for p in models["parameters"]}
    assert parameters["page"]["minimum"] == 1 and parameters["page"]["maximum"] == 1_000_000
    assert parameters["page_size"]["maximum"] == 100
    images = schema["paths"]["/api/v1/device-models/{model_id}/reference-images"]["post"]
    body = images["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert set(body["required"]) == {"file", "version"}
    assert body["properties"]["version"]["maximum"] == 2_147_483_647
    content = schema["paths"][
        "/api/v1/device-models/{model_id}/reference-images/{image_id}/content"
    ]["get"]
    assert set(content["responses"]["200"]["content"]) == {"image/jpeg", "image/png", "image/webp"}
    delete = schema["paths"]["/api/v1/device-models/{model_id}/reference-images/{image_id}"][
        "delete"
    ]
    assert "X-Model-Version" in delete["responses"]["204"]["headers"]
    assert "content" not in delete["responses"]["204"]
    public_fields = schema["components"]["schemas"]["ImageOutput"]["properties"]
    assert not {"storage_key", "path", "password_hash"} & public_fields.keys()


def test_asset_contract_versions_immutability_and_scope(client):
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert set(paths["/api/v1/assets"]) == {"get", "post"}
    assert set(paths["/api/v1/assets/{asset_id}"]) == {"get", "patch"}
    patch = schema["components"]["schemas"]["AssetPatch"]
    assert "asset_code" not in patch["properties"] and patch["additionalProperties"] is False
    assert patch["properties"]["version"]["maximum"] == 2_147_483_647
    assert "asset_version" in schema["components"]["schemas"]["IdentifierCreate"]["required"]
    assert {"version", "asset_version"} <= set(
        schema["components"]["schemas"]["IdentifierPatch"]["required"]
    )
    delete = paths["/api/v1/assets/{asset_id}/identifiers/{identifier_id}"]["delete"]
    assert {p["name"] for p in delete["parameters"] if p["in"] == "query" and p["required"]} == {
        "version",
        "asset_version",
    }
    assert set(paths["/api/v1/assets/imports/preview"]) == {"post"}
    assert set(paths["/api/v1/assets/imports/commit"]) == {"post"}
    assert set(paths["/api/v1/assets/export.csv"]) == {"get"}
