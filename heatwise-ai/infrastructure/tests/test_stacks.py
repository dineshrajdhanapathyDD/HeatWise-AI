"""Template assertions for the HeatWise CDK app. Pure synth: no AWS calls, no Docker."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from aws_cdk.assertions import Match, Template

INFRA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INFRA))

from app import build_app  # noqa: E402
from stacks.bedrock_routes import bedrock_resources  # noqa: E402

ACCOUNT = "123456789012"
PROFILE = "us.amazon.nova-2-lite-v1:0"


@pytest.fixture
def stub_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("CDK_DEFAULT_ACCOUNT", ACCOUNT)
    asset = tmp_path / "lambda"
    (asset / "backend").mkdir(parents=True)
    (asset / "backend" / "__init__.py").write_text("", encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>t</title>", encoding="utf-8")
    return asset, dist


def _context(asset: Path, dist: Path, **overrides) -> dict:
    ctx = json.loads((INFRA / "cdk.json").read_text(encoding="utf-8"))["context"]
    ctx.update({"heatwise:lambda_asset_dir": str(asset), "heatwise:frontend_dist": str(dist)})
    ctx.update(overrides)
    return ctx


def _templates(stub_dirs, **overrides) -> dict[str, Template]:
    asset, dist = stub_dirs
    app = build_app(_context(asset, dist, **overrides))
    return {stack.stack_name: Template.from_stack(stack) for stack in app.node.children
            if hasattr(stack, "stack_name")}


@pytest.fixture
def templates(stub_dirs):
    return _templates(stub_dirs)


def _statements(template: Template) -> list[dict]:
    out = []
    for res in template.find_resources("AWS::IAM::Policy").values():
        out.extend(res["Properties"]["PolicyDocument"]["Statement"])
    for res in template.find_resources("AWS::IAM::Role").values():
        for policy in res["Properties"].get("Policies", []):
            out.extend(policy["PolicyDocument"]["Statement"])
    return out


def _as_list(value):
    return value if isinstance(value, list) else [value]


def test_default_stacks(templates):
    assert set(templates) == {"HeatWiseData", "HeatWiseApi"}


def test_no_rest_api_account_or_vpc(stub_dirs):
    for template in _templates(stub_dirs, **{"heatwise:frontend": True}).values():
        types = {r["Type"] for r in template.to_json()["Resources"].values()}
        assert "AWS::ApiGateway::Account" not in types
        assert "AWS::ApiGateway::RestApi" not in types
        assert not [t for t in types if t.startswith("AWS::EC2::")]


def test_tables(templates):
    data = templates["HeatWiseData"]
    data.resource_count_is("AWS::DynamoDB::Table", 2)
    tables = data.find_resources("AWS::DynamoDB::Table")
    assert all(t["Properties"]["BillingMode"] == "PAY_PER_REQUEST" for t in tables.values())
    data.has_resource_properties("AWS::DynamoDB::Table", {
        "KeySchema": [{"AttributeName": "report_id", "KeyType": "HASH"}],
        "GlobalSecondaryIndexes": Match.array_with([
            {"IndexName": "by_location",
             "KeySchema": [{"AttributeName": "location_key", "KeyType": "HASH"},
                           {"AttributeName": "created_at", "KeyType": "RANGE"}],
             "Projection": {"ProjectionType": "ALL"}},
            {"IndexName": "by_created",
             "KeySchema": [{"AttributeName": "entity", "KeyType": "HASH"},
                           {"AttributeName": "created_at", "KeyType": "RANGE"}],
             "Projection": {"ProjectionType": "ALL"}},
        ]),
    })
    data.has_resource_properties("AWS::DynamoDB::Table", {
        "KeySchema": [{"AttributeName": "job_id", "KeyType": "HASH"}],
        "GlobalSecondaryIndexes": [
            {"IndexName": "pending",
             "KeySchema": [{"AttributeName": "pending_pk", "KeyType": "HASH"},
                           {"AttributeName": "created_at", "KeyType": "RANGE"}],
             "Projection": {"ProjectionType": "KEYS_ONLY"}},
        ],
        "TimeToLiveSpecification": {"AttributeName": "expires_at", "Enabled": True},
    })
    for table in data.find_resources("AWS::DynamoDB::Table").values():
        assert table["DeletionPolicy"] == "Retain"


def test_sessions_bucket(templates):
    data = templates["HeatWiseData"]
    data.has_resource_properties("AWS::S3::Bucket", {
        "BucketEncryption": {"ServerSideEncryptionConfiguration": [
            {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]},
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True, "BlockPublicPolicy": True,
            "IgnorePublicAcls": True, "RestrictPublicBuckets": True},
        "LifecycleConfiguration": {"Rules": [Match.object_like(
            {"Prefix": "sessions/", "ExpirationInDays": 30, "Status": "Enabled"})]},
    })
    data.has_resource_properties("AWS::S3::BucketPolicy", {
        "PolicyDocument": {"Statement": Match.array_with([Match.object_like({
            "Effect": "Deny",
            "Condition": {"Bool": {"aws:SecureTransport": "false"}},
        })])},
    })


def test_log_groups_have_retention(templates):
    for template in templates.values():
        for group in template.find_resources("AWS::Logs::LogGroup").values():
            assert group["Properties"]["RetentionInDays"] == 14
    templates["HeatWiseApi"].resource_count_is("AWS::Logs::LogGroup", 3)


def test_functions(templates):
    api = templates["HeatWiseApi"]
    functions = api.find_resources("AWS::Lambda::Function")
    assert len(functions) == 2
    for fn in functions.values():
        assert fn["Properties"]["Architectures"] == ["arm64"]
        assert fn["Properties"]["Runtime"] == "python3.13"
    handlers = {fn["Properties"]["Handler"] for fn in functions.values()}
    assert handlers == {"backend.lambda_worker.handler", "backend.lambda_api.handler"}
    api.has_resource_properties("AWS::Lambda::EventInvokeConfig", {
        "MaximumRetryAttempts": 0, "MaximumEventAgeInSeconds": 120})
    worker_env = next(fn for fn in functions.values()
                      if fn["Properties"]["Handler"] == "backend.lambda_worker.handler"
                      )["Properties"]["Environment"]["Variables"]
    # event age + worker timeout must fit the stale window the API reports against
    assert 120 + 300 <= int(worker_env["JOB_STALE_AFTER_SECONDS"])
    api.has_resource_properties("AWS::Lambda::Function", {
        "Handler": "backend.lambda_worker.handler", "MemorySize": 1024, "Timeout": 300,
        "Environment": {"Variables": Match.object_like({
            "AGENT_MODE": "bedrock", "SESSION_STORAGE": "s3", "JOB_STORE": "dynamodb",
            "ASSESSMENT_STORE": "dynamodb", "BEDROCK_MODEL_ID": PROFILE})},
    })
    api_env = next(fn for fn in functions.values()
                   if fn["Properties"]["Handler"] == "backend.lambda_api.handler"
                   )["Properties"]["Environment"]["Variables"]
    assert api_env["JOB_DISPATCH"] == "lambda"
    assert json.loads(api_env["API_CORS_ORIGINS"]) == [
        "http://localhost:5173", "http://127.0.0.1:5173"]
    assert not {"BEDROCK_MODEL_ID", "SESSION_BUCKET"} & set(api_env)


def test_roles_have_no_managed_policies(templates):
    for role in templates["HeatWiseApi"].find_resources("AWS::IAM::Role").values():
        assert not role["Properties"].get("ManagedPolicyArns")


def test_iam_least_privilege(templates):
    statements = [s for t in templates.values() for s in _statements(t)]
    assert statements
    for statement in statements:
        actions = _as_list(statement["Action"])
        assert not [a for a in actions if "*" in a], statement
        if any(a.split(":")[0] in {"dynamodb", "s3", "bedrock", "lambda"} for a in actions):
            assert "*" not in _as_list(statement["Resource"]), statement


def test_api_role_checklist_update(templates):
    """D-M5-9: the API role may UpdateItem on the assessments table only (no index ARN, no '*')."""
    api = templates["HeatWiseApi"]
    roles = api.find_resources("AWS::IAM::Role")
    api_role = next(k for k in roles if k.startswith("ApiRole"))
    statements = [s for p in api.find_resources("AWS::IAM::Policy").values()
                  if {"Ref": api_role} in p["Properties"]["Roles"]
                  for s in p["Properties"]["PolicyDocument"]["Statement"]]
    reads = [s for s in statements if sorted(_as_list(s["Action"])) == ["dynamodb:GetItem", "dynamodb:Query"]]
    assert len(reads) == 1
    assessments_arn = _as_list(reads[0]["Resource"])[0]
    updates = [s for s in statements if "dynamodb:UpdateItem" in _as_list(s["Action"])
               and assessments_arn in _as_list(s["Resource"])]
    assert len(updates) == 1
    assert _as_list(updates[0]["Action"]) == ["dynamodb:UpdateItem"]
    assert _as_list(updates[0]["Resource"]) == [assessments_arn]
    for statement in statements:
        assert "*" not in _as_list(statement["Resource"]), statement


def test_list_bucket_unconditioned(templates):
    """Missing session.json must return 404 (not 403) to the worker for new S3 sessions."""
    listing = [s for s in _statements(templates["HeatWiseApi"])
               if "s3:ListBucket" in _as_list(s["Action"])]
    assert len(listing) == 1
    assert "Condition" not in listing[0]
    assert not isinstance(listing[0]["Resource"], list)  # the sessions bucket only


def test_bedrock_scope(templates):
    bedrock = [s for s in _statements(templates["HeatWiseApi"])
               if any(a.startswith("bedrock:") for a in _as_list(s["Action"]))]
    assert len(bedrock) == 1
    assert sorted(bedrock[0]["Action"]) == [
        "bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    assert bedrock[0]["Resource"] == [
        f"arn:aws:bedrock:us-east-1:{ACCOUNT}:inference-profile/{PROFILE}",
        "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-2-lite-v1:0",
        "arn:aws:bedrock:us-east-2::foundation-model/amazon.nova-2-lite-v1:0",
        "arn:aws:bedrock:us-west-2::foundation-model/amazon.nova-2-lite-v1:0",
    ]


def test_http_api_stage(templates):
    api = templates["HeatWiseApi"]
    api.resource_count_is("AWS::ApiGatewayV2::Api", 1)
    api.has_resource_properties("AWS::ApiGatewayV2::Api", {"ProtocolType": "HTTP"})
    stage = next(iter(api.find_resources("AWS::ApiGatewayV2::Stage").values()))["Properties"]
    assert stage["StageName"] == "$default"
    assert "DestinationArn" in stage["AccessLogSettings"]
    assert "$context.requestId" in stage["AccessLogSettings"]["Format"]
    assert stage["DefaultRouteSettings"] == {
        "ThrottlingRateLimit": 5, "ThrottlingBurstLimit": 10}
    assert "CorsConfiguration" not in next(
        iter(api.find_resources("AWS::ApiGatewayV2::Api").values()))["Properties"]


def test_frontend_stack_optional(stub_dirs):
    templates = _templates(stub_dirs, **{"heatwise:frontend": "true"})
    assert set(templates) == {"HeatWiseData", "HeatWiseApi", "HeatWiseFrontend"}
    site = templates["HeatWiseFrontend"]
    site.resource_count_is("AWS::CloudFront::Distribution", 1)
    site.resource_count_is("AWS::CloudFront::OriginAccessControl", 1)
    site.resource_count_is("AWS::CloudFront::Function", 1)
    dist = next(iter(site.find_resources("AWS::CloudFront::Distribution").values()))
    config = dist["Properties"]["DistributionConfig"]
    assert config["DefaultCacheBehavior"]["ViewerProtocolPolicy"] == "redirect-to-https"
    assert [b["PathPattern"] for b in config["CacheBehaviors"]] == ["/api/*"]
    assert "CustomErrorResponses" not in config
    groups = site.find_resources("AWS::Logs::LogGroup").values()
    assert groups and all(g["Properties"]["RetentionInDays"] == 14 for g in groups)
    site.has_resource_properties("AWS::S3::Bucket", {
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True, "BlockPublicPolicy": True,
            "IgnorePublicAcls": True, "RestrictPublicBuckets": True}})


def test_bedrock_resources_unknown_region():
    with pytest.raises(ValueError, match="model-card-amazon-nova-2-lite"):
        bedrock_resources(PROFILE, "eu-west-1", ACCOUNT)


def test_missing_asset_dir(stub_dirs, tmp_path):
    _, dist = stub_dirs
    with pytest.raises(FileNotFoundError, match="build_lambda_asset.py"):
        build_app(_context(tmp_path / "missing", dist))
