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
  - model_name: together_ai/meta-llama/Llama-3-8b-chat-hf
    litellm_params:
      model: together_ai/meta-llama/Llama-3-8b-chat-hf
      api_key: "os.environ/TOGETHER_API_KEY"

litellm_settings:
  drop_params: true
  set_verbose: false

general_settings:
  master_key: "os.environ/LITELLM_MASTER_KEY"
  callbacks: ["langfuse"]

environment_variables:
  LANGFUSE_HOST: "${langfuse_host}"
  LANGFUSE_PUBLIC_KEY: "os.environ/LANGFUSE_PUBLIC_KEY"
  LANGFUSE_SECRET_KEY: "os.environ/LANGFUSE_SECRET_KEY"
