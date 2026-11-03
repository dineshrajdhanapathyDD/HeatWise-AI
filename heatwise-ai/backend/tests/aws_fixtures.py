"""moto fixtures and table helpers. Tests never reach real AWS: fake credentials + mock_aws.

Import the fixtures into a test module: `from backend.tests.aws_fixtures import aws, aws_credentials`.
"""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from backend.session import dynamodb_schema as schema

REGION = "us-east-1"


@pytest.fixture
def aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN"):
        monkeypatch.setenv(name, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.delenv("AWS_PROFILE", raising=False)


@pytest.fixture
def aws(aws_credentials):
    with mock_aws():
        yield


def _s(name: str) -> dict:
    return {"AttributeName": name, "AttributeType": "S"}


def _gsi(name: str, pk: str, sk: str) -> dict:
    return {"IndexName": name, "Projection": {"ProjectionType": "ALL"},
            "KeySchema": [{"AttributeName": pk, "KeyType": "HASH"}, {"AttributeName": sk, "KeyType": "RANGE"}]}


def create_assessments_table(client, name: str) -> None:
    client.create_table(
        TableName=name, BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[_s(schema.ASSESSMENTS_PK), _s(schema.BY_LOCATION_PK), _s(schema.BY_CREATED_PK),
                              _s(schema.CREATED_AT)],
        KeySchema=[{"AttributeName": schema.ASSESSMENTS_PK, "KeyType": "HASH"}],
        GlobalSecondaryIndexes=[_gsi(schema.BY_LOCATION_INDEX, schema.BY_LOCATION_PK, schema.CREATED_AT),
                                _gsi(schema.BY_CREATED_INDEX, schema.BY_CREATED_PK, schema.CREATED_AT)],
    )


def create_jobs_table(client, name: str) -> None:
    client.create_table(
        TableName=name, BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[_s(schema.JOBS_PK), _s(schema.PENDING_PK), _s(schema.CREATED_AT)],
        KeySchema=[{"AttributeName": schema.JOBS_PK, "KeyType": "HASH"}],
        GlobalSecondaryIndexes=[_gsi(schema.PENDING_INDEX, schema.PENDING_PK, schema.CREATED_AT)],
    )
    client.update_time_to_live(TableName=name, TimeToLiveSpecification={"Enabled": True,
                                                                         "AttributeName": schema.TTL_ATTR})


def create_bucket(name: str) -> None:
    boto3.client("s3", region_name=REGION).create_bucket(Bucket=name)
