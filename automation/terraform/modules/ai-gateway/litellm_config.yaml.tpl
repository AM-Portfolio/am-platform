# LiteLLM routing configuration template
model_list:
  - model_name: deepseek-chat
    litellm_params:
      model: deepseek/deepseek-chat
      api_key: "os.environ/DEEPSEEK_API_KEY"
  - model_name: gemini-1.5-pro
    litellm_params:
      model: gemini/gemini-1.5-pro
      api_key: "os.environ/GOOGLE_API_KEY"
  - model_name: gemini-1.5-flash
    litellm_params:
      model: gemini/gemini-1.5-flash
      api_key: "os.environ/GOOGLE_API_KEY"
  - model_name: together_ai/meta-llama/Meta-Llama-3-8B-Instruct-Lite
    litellm_params:
      model: together_ai/meta-llama/Meta-Llama-3-8B-Instruct-Lite
      api_key: "os.environ/TOGETHER_API_KEY"
  - model_name: Qwen/Qwen3-VL-8B-Instruct
    litellm_params:
      model: together_ai/Qwen/Qwen3-VL-8B-Instruct
      api_key: "os.environ/TOGETHER_API_KEY"

litellm_settings:
  drop_params: true
  set_verbose: false
  success_callback: ["langfuse"]
  failure_callback: ["langfuse"]

general_settings:
  master_key: "os.environ/LITELLM_MASTER_KEY"
  # Required for LiteLLM Admin UI to show request/response on Logs page.
  store_model_in_db: true
  store_prompts_in_spend_logs: true

environment_variables:
  LANGFUSE_HOST: "${langfuse_host}"
  LANGFUSE_PUBLIC_KEY: "os.environ/LANGFUSE_PUBLIC_KEY"
  LANGFUSE_SECRET_KEY: "os.environ/LANGFUSE_SECRET_KEY"

# MCP tools — OpenAPI auto-register from am-mcp-gateway (manifest sync sets allowed_tools)
mcp_servers:
  am_mcp_gateway:
    transport: http
    url: http://am-mcp-gateway.am-apps-preprod.svc.cluster.local:8120
    spec_path: http://am-mcp-gateway.am-apps-preprod.svc.cluster.local:8120/openapi.json
    allow_all_keys: true
    allowed_tools:
      - am_mcp_gateway-run_modern_ui_auth_test
    description: "AM MCP Gateway — UI test tools from module testing manifests"
