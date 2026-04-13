classroom_ai/
  app/
    main.py                 # FastAPI app, /health
    core/
      config.py             # env: provider, models, keys
    api/
      v1/
        router.py
        endpoints/
          explain.py        # POST /text, POST /images
    schemas/
      explain.py            # request/response models
    services/
      explanation.py        # prompts + orchestration + JSON parse
      llm/
        protocol.py         # LLMProvider interface
        types.py            # message shapes (text + image_url)
        factory.py          # openai | ollama
        openai_provider.py
        ollama_provider.py
  requirements.txt
  .env.example
  .gitignore