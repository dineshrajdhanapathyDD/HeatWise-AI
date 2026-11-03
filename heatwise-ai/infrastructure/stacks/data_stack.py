"""HeatWiseData: assessment and job tables plus the private sessions bucket (D-M4-5, D-M4-6)."""
from __future__ import annotations

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_s3 as s3
from constructs import Construct

from backend.session import dynamodb_schema as schema

_S = dynamodb.AttributeType.STRING


class HeatWiseDataStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, removal: str = "retain",
                 session_prefix: str = "sessions", **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        policy = RemovalPolicy.DESTROY if removal == "destroy" else RemovalPolicy.RETAIN

        self.assessments_table = dynamodb.Table(
            self, "Assessments",
            partition_key=dynamodb.Attribute(name=schema.ASSESSMENTS_PK, type=_S),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.DEFAULT,
            removal_policy=policy,
        )
        self.assessments_table.add_global_secondary_index(
            index_name=schema.BY_LOCATION_INDEX,
            partition_key=dynamodb.Attribute(name=schema.BY_LOCATION_PK, type=_S),
            sort_key=dynamodb.Attribute(name=schema.CREATED_AT, type=_S),
            projection_type=dynamodb.ProjectionType.ALL,
        )
        self.assessments_table.add_global_secondary_index(
            index_name=schema.BY_CREATED_INDEX,
            partition_key=dynamodb.Attribute(name=schema.BY_CREATED_PK, type=_S),
            sort_key=dynamodb.Attribute(name=schema.CREATED_AT, type=_S),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        self.jobs_table = dynamodb.Table(
            self, "Jobs",
            partition_key=dynamodb.Attribute(name=schema.JOBS_PK, type=_S),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.DEFAULT,
            time_to_live_attribute=schema.TTL_ATTR,
            removal_policy=policy,
        )
        self.jobs_table.add_global_secondary_index(
            index_name=schema.PENDING_INDEX,
            partition_key=dynamodb.Attribute(name=schema.PENDING_PK, type=_S),
            sort_key=dynamodb.Attribute(name=schema.CREATED_AT, type=_S),
            projection_type=dynamodb.ProjectionType.KEYS_ONLY,
        )

        self.session_prefix = session_prefix
        self.sessions_bucket = s3.Bucket(
            self, "Sessions",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            versioned=False,
            lifecycle_rules=[s3.LifecycleRule(
                id="ExpireSessions", prefix=f"{session_prefix}/", expiration=Duration.days(30),
            )],
            removal_policy=policy,
        )
