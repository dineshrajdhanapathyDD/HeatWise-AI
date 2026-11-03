"""Optional Amazon Bedrock AgentCore Runtime entrypoint (Milestone 4, D-M4-9).

Not deployed by this project; see docs/deployment.md. Needs the `agentcore` extra
(`bedrock-agentcore==1.25.2`), which is not part of the Lambda asset. Run locally with
`python -m backend.agentcore_entry`.
"""

from __future__ import annotations

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from backend.agentcore_handler import run_assessment

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload, context):
    return run_assessment(payload, getattr(context, "session_id", None))


if __name__ == "__main__":
    app.run()
