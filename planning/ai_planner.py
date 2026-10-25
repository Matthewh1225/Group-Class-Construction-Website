import json
import os

from google import genai
from groq import BadRequestError, Groq
from openrouter import OpenRouter

from .ai_config import AI_TIMEOUT, MODELS
from .schemas import PlanningError


def make_client(provider, key_name):
    api_key = os.getenv(key_name)
    if not api_key:
        return None
    if provider == "gemini":
        return genai.Client(api_key=api_key)
    if provider == "groq":
        return Groq(api_key=api_key)
    return OpenRouter(api_key=api_key)


AI_MODELS = {}
for model_name, settings in MODELS.items():
    AI_MODELS[model_name] = {
        "provider": settings["provider"],
        "client": make_client(settings["provider"], settings["api_key"]),
        "model": os.getenv(settings["model_env"]) or settings["default"],
    }


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
        "response_mime_type": "application/json",
        "response_json_schema": response_schema,
    }

    response = model["client"].models.generate_content(
        model=model["model"],
        contents=prompt,
        config=config,
    )
    # A blocked response may have no candidates.
    finish_reason = None
    if response.candidates:
        finish_reason = response.candidates[0].finish_reason
    return {"text": response.text or "", "finish_reason": finish_reason}


def call_groq(model, prompt, thinking_level, system_instruction, response_schema,
              output_tokens):
    try:
        response = model["client"].with_options(max_retries=0).chat.completions.create(
            model=model["model"],
            messages=make_messages(system_instruction, prompt),
            temperature=0.5,
            max_completion_tokens=output_tokens,
            reasoning_effort=thinking_level,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema["title"],
                    "strict": True,
                    "schema": response_schema,
                },
            },
            timeout=AI_TIMEOUT,
        )
    except BadRequestError as error:
        if "json_validate_failed" in str(error.body):
            raise PlanningError("the AI answer did not match the required format") from error
        raise
    if not response.choices:
        raise PlanningError("the AI provider returned an empty answer")
    choice = response.choices[0]
    return {"text": choice.message.content or "", "finish_reason": choice.finish_reason}


def call_openrouter(model, prompt, thinking_level, system_instruction, response_schema,
                    output_tokens):
    prompt += "\nReturn only one JSON object matching this schema:\n" + json.dumps(response_schema)
    options = {
        "model": model["model"],
        "messages": make_messages(system_instruction, prompt),
        "reasoning": {"effort": thinking_level, "exclude": True},
        "provider": {"require_parameters": True, "allow_fallbacks": False},
        "max_tokens": output_tokens,
        "stream": False,
        "timeout_ms": AI_TIMEOUT * 1000,
        "retries": None,
    }

    response = model["client"].chat.send(**options)
    if not response.choices:
        raise PlanningError("the AI provider returned an empty answer")
    choice = response.choices[0]
    return {"text": choice.message.content or "", "finish_reason": choice.finish_reason}


def ask_model(model_name, prompt, reasoning, instructions, schema, output_tokens):
    model = AI_MODELS[model_name]
    if model["client"] is None:
        raise PlanningError(f"The {model_name} AI model is not configured.")
    if model["provider"] == "gemini":
        result = call_gemini(model, prompt, reasoning, instructions, schema, output_tokens)
    elif model["provider"] == "groq":
        result = call_groq(model, prompt, reasoning, instructions, schema, output_tokens)
    elif model["provider"] == "openrouter":
        result = call_openrouter(model, prompt, reasoning, instructions, schema, output_tokens)
    else:
        raise PlanningError(f"Unsupported AI provider: {model['provider']}")
    # Gemini uses STOP; the other providers use stop.
    if result["finish_reason"] not in ("stop", "STOP"):
        raise PlanningError("the AI answer was cut off before it finished")
    return result["text"]

