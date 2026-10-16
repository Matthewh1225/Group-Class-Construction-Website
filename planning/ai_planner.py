import json
import os
from time import monotonic

from google import genai
from groq import Groq
from openrouter import OpenRouter

from .ai_config import AI_TIMEOUT, MODEL_CAPABILITIES, MODELS


def make_client(provider, key_name):
    api_key = os.getenv(key_name)
    if not api_key:
        return None
    if provider == "gemini":
        return genai.Client(api_key=api_key)
    if provider == "groq":
        return Groq(api_key=api_key)
    return OpenRouter(api_key=api_key)


# A model ID set in .env always wins over the default in ai_config.
AI_MODELS = {}
for model_name, settings in MODELS.items():
    AI_MODELS[model_name] = {
        "provider": settings["provider"],
        "client": make_client(settings["provider"], settings["api_key"]),
        "model": os.getenv(settings["model_env"]) or settings["default"],
    }


def get_value(item, name, default=None):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def make_messages(system_instruction, prompt):
    return [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": prompt},
    ]


def call_gemini(model, prompt, thinking_level, system_instruction, response_schema,
                output_tokens):
    config = {
        "system_instruction": system_instruction,
        "thinking_config": {"thinking_level": thinking_level},
        "max_output_tokens": output_tokens,
        "http_options": {"timeout": AI_TIMEOUT * 1000, "retry_options": {"attempts": 1}},
        "automatic_function_calling": {"disable": True},
        # Gemini can be made to follow the JSON schema exactly
        "response_mime_type": "application/json",
        "response_json_schema": response_schema,
    }

    response = model["client"].models.generate_content(
        model=model["model"],
        contents=prompt,
        config=config,
    )
    usage = get_value(response, "usage_metadata")
    candidates = get_value(response, "candidates", []) or []
    finish_reason = None
    if isinstance(candidates, list) and candidates:
        finish_reason = str(get_value(candidates[0], "finish_reason", ""))
    return {
        "text": get_value(response, "text", "") or "",
        "thinking_tokens": get_value(usage, "thoughts_token_count"),
        "input_tokens": get_value(usage, "prompt_token_count"),
        "output_tokens": get_value(usage, "candidates_token_count"),
        "total_tokens": get_value(usage, "total_token_count"),
        "finish_reason": finish_reason,
    }


def call_groq(model, prompt, thinking_level, system_instruction, response_schema,
              output_tokens):
    # Groq can reject a full estimate during constrained generation with HTTP 400.
    # JSON object mode still gives parseable JSON; Pydantic and Python check it later.
    prompt += "\nReturn one JSON object matching this schema:\n" + json.dumps(response_schema)
    response = model["client"].with_options(max_retries=0).chat.completions.create(
        model=model["model"],
        messages=make_messages(system_instruction, prompt),
        temperature=0.5,
        max_completion_tokens=output_tokens,
        reasoning_effort=thinking_level,
        response_format={"type": "json_object"},
        timeout=AI_TIMEOUT,
    )
    usage = response.usage
    token_details = get_value(usage, "completion_tokens_details")
    choice = response.choices[0]
    message = choice.message
    return {
        "text": message.content or "",
        "thinking_tokens": get_value(token_details, "reasoning_tokens"),
        "input_tokens": get_value(usage, "prompt_tokens"),
        "output_tokens": get_value(usage, "completion_tokens"),
        "total_tokens": get_value(usage, "total_tokens"),
        "finish_reason": get_value(choice, "finish_reason"),
    }


def call_openrouter(model, prompt, thinking_level, system_instruction, response_schema,
                    output_tokens):
    # The OpenRouter model does not promise to follow a JSON schema, so the schema is sent in the prompt and Pydantic checks the JSON it returns.
    prompt += "\nReturn only one JSON object matching this schema:\n" + json.dumps(response_schema)
    options = {
        "model": model["model"],
        "messages": make_messages(system_instruction, prompt),
        "reasoning": {"effort": thinking_level, "exclude": True},
        "provider": {"require_parameters": True},
        "max_tokens": output_tokens,
        "stream": False,
        "timeout_ms": AI_TIMEOUT * 1000,
        "retries": None,
    }

    response = model["client"].chat.send(**options)
    usage = get_value(response, "usage")
    token_details = get_value(usage, "completion_tokens_details")
    choices = get_value(response, "choices", [])
    choice = choices[0]
    message = get_value(choice, "message")
    return {
        "text": get_value(message, "content", "") or "",
        "thinking_tokens": get_value(token_details, "reasoning_tokens"),
        "input_tokens": get_value(usage, "prompt_tokens"),
        "output_tokens": get_value(usage, "completion_tokens"),
        "total_tokens": get_value(usage, "total_tokens"),
        "finish_reason": get_value(choice, "finish_reason"),
    }


def check_model(model_name, reasoning):
    model = AI_MODELS[model_name]
    if model["client"] is None or not model["model"]:
        raise ValueError(f"{model_name} is not configured.")
    capability = MODEL_CAPABILITIES.get(model["model"])
    if capability is None or reasoning not in capability["levels"]:
        raise ValueError(f"{model_name} has no verified {reasoning} reasoning configuration.")
    return model, capability


def ask_model(model_name, prompt, reasoning, instructions, schema, output_tokens):
    # status is "completed" only when the model stopped normally; anything else (out of tokens, blocked) means the JSON may be cut off.
    model, capability = check_model(model_name, reasoning)
    if output_tokens > capability["output_limit"]:
        raise ValueError("The requested output size exceeds this model's documented limit.")

    # monotonic measures elapsed time even if the system clock changes
    started_at = monotonic()
    if model["provider"] == "gemini":
        result = call_gemini(model, prompt, reasoning, instructions, schema, output_tokens)
    elif model["provider"] == "groq":
        result = call_groq(model, prompt, reasoning, instructions, schema, output_tokens)
    elif model["provider"] == "openrouter":
        result = call_openrouter(model, prompt, reasoning, instructions, schema, output_tokens)
    else:
        raise ValueError(f"Unsupported AI provider: {model['provider']}")
    result["elapsed_seconds"] = round(monotonic() - started_at, 2)

    if result["finish_reason"] in {"stop", "STOP", "FinishReason.STOP"}:
        result["status"] = "completed"
    else:
        result["status"] = "incomplete"
    return result

