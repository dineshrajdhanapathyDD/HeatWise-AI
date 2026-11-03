"""Where a Bedrock cross-Region inference profile may route a request (D-M4-7).

Source: https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html
(section "Geo inference details", Geo US), checked 2026-11-03.

Invoking an inference profile needs permission on the profile in the source Region and on the
foundation model in every destination Region the profile can route to. Only verified
(profile, source Region) pairs are listed; anything else fails synth instead of guessing.
"""
from __future__ import annotations

DOC_URL = "https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html"

_NOVA_2_LITE_US = "us.amazon.nova-2-lite-v1:0"
_US_EAST_WEST = ("us-east-1", "us-east-2", "us-west-2")

ROUTES: dict[tuple[str, str], tuple[str, ...]] = {
    (_NOVA_2_LITE_US, "us-east-1"): _US_EAST_WEST,
    (_NOVA_2_LITE_US, "us-east-2"): _US_EAST_WEST,
    (_NOVA_2_LITE_US, "us-west-2"): _US_EAST_WEST,
    (_NOVA_2_LITE_US, "us-west-1"): ("us-east-1", "us-east-2", "us-west-1", "us-west-2"),
}


def bedrock_resources(profile_id: str, region: str, account: str) -> list[str]:
    """Inference-profile ARN plus one foundation-model ARN per destination Region."""
    destinations = ROUTES.get((profile_id, region))
    if destinations is None:
        raise ValueError(
            f"No verified Bedrock routing for inference profile {profile_id!r} from {region!r}. "
            f"Check the destination Regions in {DOC_URL} and add them to "
            "infrastructure/stacks/bedrock_routes.py."
        )
    model_id = profile_id.split(".", 1)[1]  # drop the geo prefix, e.g. "us."
    return [f"arn:aws:bedrock:{region}:{account}:inference-profile/{profile_id}"] + [
        f"arn:aws:bedrock:{dest}::foundation-model/{model_id}" for dest in destinations
    ]
