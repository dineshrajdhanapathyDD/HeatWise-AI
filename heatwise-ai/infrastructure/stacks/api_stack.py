"""HeatWiseApi: API and worker Lambdas, least-privilege roles, log groups and the HTTP API.

D-M4-1..4, D-M4-7. Both functions share one zip asset built without Docker by
infrastructure/scripts/build_lambda_asset.py. HTTP APIs do not use the account-level API
Gateway CloudWatch role, so this stack never creates AWS::ApiGateway::Account.
"""
from __future__ import annotations

import json

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as integrations
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

from backend.session import dynamodb_schema as schema

from .bedrock_routes import bedrock_resources
from .data_stack import HeatWiseDataStack

_RETENTION = {
    1: logs.RetentionDays.ONE_DAY,
    3: logs.RetentionDays.THREE_DAYS,
    5: logs.RetentionDays.FIVE_DAYS,
    7: logs.RetentionDays.ONE_WEEK,
    14: logs.RetentionDays.TWO_WEEKS,
    30: logs.RetentionDays.ONE_MONTH,
    60: logs.RetentionDays.TWO_MONTHS,
    90: logs.RetentionDays.THREE_MONTHS,
}

# Field set from the API Gateway HTTP API access logging documentation.
_ACCESS_LOG_FORMAT = json.dumps({
    "requestId": "$context.requestId",
    "ip": "$context.identity.sourceIp",
    "requestTime": "$context.requestTime",
    "httpMethod": "$context.httpMethod",
    "routeKey": "$context.routeKey",
    "status": "$context.status",
    "protocol": "$context.protocol",
    "responseLength": "$context.responseLength",
    "integrationErrorMessage": "$context.integrationErrorMessage",
})


def _retention(days: int) -> logs.RetentionDays:
    try:
        return _RETENTION[int(days)]
    except KeyError as exc:
        raise ValueError(
            f"heatwise:log_retention_days must be one of {sorted(_RETENTION)}"
        ) from exc


class HeatWiseApiStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, data: HeatWiseDataStack,
                 asset_dir: str, model_id: str, cors_origins: list[str], version: str,
                 log_retention_days: int = 14, throttle_rate: float = 5,
                 throttle_burst: int = 10, max_pending_jobs: int = 20, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        retention = _retention(log_retention_days)
        code = lambda_.Code.from_asset(asset_dir)
        jobs = data.jobs_table
        assessments = data.assessments_table
        bucket = data.sessions_bucket
        prefix = data.session_prefix

        def log_group(name: str) -> logs.LogGroup:
            return logs.LogGroup(self, name, retention=retention,
                                 removal_policy=RemovalPolicy.DESTROY)

        worker_logs = log_group("WorkerLogs")
        api_logs = log_group("ApiLogs")
        access_logs = log_group("HttpApiAccessLogs")

        def role(name: str, description: str) -> iam.Role:
            return iam.Role(self, name, description=description,
                            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"))

        # Worker role: run one assessment and store the result.
        worker_role = role("WorkerRole", "HeatWise worker Lambda - runs assessment jobs")
        worker_role.add_to_policy(iam.PolicyStatement(
            actions=["logs:CreateLogStream", "logs:PutLogEvents"],
            resources=[worker_logs.log_group_arn]))
        worker_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:GetItem", "dynamodb:UpdateItem"],
            resources=[jobs.table_arn]))
        worker_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:PutItem"],
            resources=[assessments.table_arn]))
        worker_role.add_to_policy(iam.PolicyStatement(
            actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
            resources=[bucket.arn_for_objects(f"{prefix}/*")]))
        # No s3:prefix condition: GetObject/HeadObject on a missing key need an unconditioned
        # ListBucket to get 404 (Strands treats only 404/NoSuchKey as "new session"). The
        # bucket only holds sessions, so this stays least privilege.
        worker_role.add_to_policy(iam.PolicyStatement(
            actions=["s3:ListBucket"],
            resources=[bucket.bucket_arn]))
        worker_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            resources=bedrock_resources(model_id, self.region, self.account)))

        self.worker_fn = lambda_.Function(
            self, "Worker",
            description="HeatWise AI assessment worker (async invoke, one job per event)",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            handler="backend.lambda_worker.handler",
            code=code,
            memory_size=1024,
            timeout=Duration.seconds(300),
            role=worker_role,
            log_group=worker_logs,
            retry_attempts=0,
            # Event age (120 s) + worker timeout (300 s) = JOB_STALE_AFTER_SECONDS (420 s):
            # a late event never starts a job the API already reports as timed out.
            max_event_age=Duration.seconds(120),
            environment={
                "AGENT_MODE": "bedrock",
                "WEATHER_PROVIDER": "open_meteo",
                "BEDROCK_MODEL_ID": model_id,
                "ASSESSMENT_STORE": "dynamodb",
                "ASSESSMENTS_TABLE_NAME": assessments.table_name,
                "JOB_STORE": "dynamodb",
                "JOBS_TABLE_NAME": jobs.table_name,
                "JOB_STALE_AFTER_SECONDS": "420",
                "SESSION_STORAGE": "s3",
                "SESSION_BUCKET": bucket.bucket_name,
                "SESSION_PREFIX": prefix,
                "HEATWISE_VERSION": version,
                "LOG_LEVEL": "INFO",
            },
        )

        # API role: create/read jobs, read stored assessments, update checklist progress, start the worker.
        api_role = role("ApiRole", "HeatWise API Lambda - HTTP API backend")
        api_role.add_to_policy(iam.PolicyStatement(
            actions=["logs:CreateLogStream", "logs:PutLogEvents"],
            resources=[api_logs.log_group_arn]))
        api_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem",
                     "dynamodb:Query"],
            resources=[jobs.table_arn, f"{jobs.table_arn}/index/{schema.PENDING_INDEX}"]))
        api_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:GetItem", "dynamodb:Query"],
            resources=[assessments.table_arn, f"{assessments.table_arn}/index/*"]))
        # Checklist progress (D-M5-9): update one attribute of a stored assessment; table only.
        api_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:UpdateItem"],
            resources=[assessments.table_arn]))
        api_role.add_to_policy(iam.PolicyStatement(
            actions=["lambda:InvokeFunction"],
            resources=[self.worker_fn.function_arn]))

        self.api_fn = lambda_.Function(
            self, "Api",
            description="HeatWise AI HTTP API (FastAPI via Mangum)",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            handler="backend.lambda_api.handler",
            code=code,
            memory_size=512,
            timeout=Duration.seconds(29),
            role=api_role,
            log_group=api_logs,
            environment={
                "ASSESSMENT_STORE": "dynamodb",
                "ASSESSMENTS_TABLE_NAME": assessments.table_name,
                "JOB_STORE": "dynamodb",
                "JOBS_TABLE_NAME": jobs.table_name,
                "JOB_STALE_AFTER_SECONDS": "420",
                "JOB_DISPATCH": "lambda",
                "WORKER_FUNCTION_NAME": self.worker_fn.function_name,
                "API_CORS_ORIGINS": json.dumps(list(cors_origins)),
                "API_MAX_PENDING_JOBS": str(max_pending_jobs),
                "HEATWISE_VERSION": version,
                "LOG_LEVEL": "INFO",
            },
        )

        self.http_api = apigwv2.HttpApi(
            self, "HttpApi",
            description="HeatWise AI public API",
            default_integration=integrations.HttpLambdaIntegration("Api", self.api_fn),
            create_default_stage=True,
        )
        stage = self.http_api.default_stage.node.default_child
        stage.access_log_settings = apigwv2.CfnStage.AccessLogSettingsProperty(
            destination_arn=access_logs.log_group_arn, format=_ACCESS_LOG_FORMAT)
        stage.default_route_settings = apigwv2.CfnStage.RouteSettingsProperty(
            throttling_rate_limit=float(throttle_rate),
            throttling_burst_limit=int(throttle_burst))

        CfnOutput(self, "ApiUrl", value=self.http_api.api_endpoint)
