"""HeatWiseFrontend (optional, -c heatwise:frontend=true): private S3 site behind CloudFront.

The site and the API share one CloudFront origin: `/api/*` goes to the HTTP API with caching
disabled, so the browser needs no CORS. A viewer-request CloudFront Function rewrites
extension-less paths to /index.html for the SPA. No distribution-level error responses, since
they would also rewrite API 404s.
"""
from __future__ import annotations

from pathlib import Path

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct

from .api_stack import HeatWiseApiStack, _retention

_SPA_REWRITE = """
function handler(event) {
  var request = event.request;
  var last = request.uri.split('/').pop();
  if (last.indexOf('.') === -1) {
    request.uri = '/index.html';
  }
  return request;
}
"""


class HeatWiseFrontendStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, api: HeatWiseApiStack,
                 dist_dir: str, removal: str = "retain",
                 log_retention_days: int = 14, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        dist = Path(dist_dir)
        if not (dist / "index.html").is_file():
            raise FileNotFoundError(
                f"Frontend build not found at {dist}. Run `npm run build` in frontend/ "
                "(with VITE_API_BASE_URL=/) before synthesizing with heatwise:frontend=true."
            )
        policy = RemovalPolicy.DESTROY if removal == "destroy" else RemovalPolicy.RETAIN

        bucket = s3.Bucket(
            self, "Site",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            removal_policy=policy,
        )
        rewrite = cloudfront.Function(
            self, "SpaRewrite",
            code=cloudfront.FunctionCode.from_inline(_SPA_REWRITE),
            runtime=cloudfront.FunctionRuntime.JS_2_0,
        )
        api_origin = origins.HttpOrigin(
            f"{api.http_api.api_id}.execute-api.{self.region}.amazonaws.com",
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
        )
        distribution = cloudfront.Distribution(
            self, "Distribution",
            comment="HeatWise AI web app",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                function_associations=[cloudfront.FunctionAssociation(
                    function=rewrite, event_type=cloudfront.FunctionEventType.VIEWER_REQUEST)],
            ),
            additional_behaviors={
                "/api/*": cloudfront.BehaviorOptions(
                    origin=api_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=(
                        cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER),
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                ),
            },
        )
        s3deploy.BucketDeployment(
            self, "DeploySite",
            sources=[s3deploy.Source.asset(str(dist))],
            destination_bucket=bucket,
            log_group=logs.LogGroup(self, "DeploySiteLogs", retention=_retention(log_retention_days),
                                    removal_policy=RemovalPolicy.DESTROY),
        )
        CfnOutput(self, "SiteUrl", value=f"https://{distribution.distribution_domain_name}")
