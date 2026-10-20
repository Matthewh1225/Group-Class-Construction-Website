import json
import os

from google import genai
from groq import Groq
from openrouter import OpenRouter

from .ai_config import AI_TIMEOUT, MODEL_CAPABILITIES, MODELS
from .schemas import BadAnswer


# Creates the connection to an AI provider
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


# Reads a field from a dict or an object
def get_value(item, name, default=None):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def make_messages(system_instruction, prompt):
    return [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": prompt},
    ]


# Sends the prompt to Gemini and returns its text and why it stopped.
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
    candidates = get_value(response, "candidates", []) or []
    finish_reason = None
    if isinstance(candidates, list) and candidates:
        finish_reason = str(get_value(candidates[0], "finish_reason", ""))
    return {"text": get_value(response, "text", "") or "", "finish_reason": finish_reason}


# Sends the prompt to Groq and returns its text and why it stopped.
def call_groq(model, prompt, thinking_level, system_instruction, response_schema,
              output_tokens):
    # GPT-OSS supports strict JSON schemas. Pydantic and Python still check the answer.
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
    if not response.choices:
        raise BadAnswer("the AI provider returned an empty answer")
    choice = response.choices[0]
    return {"text": choice.message.content or "", "finish_reason": get_value(choice, "finish_reason")}


# Sends the prompt to OpenRouter and returns its text and why it stopped.
def call_openrouter(model, prompt, thinking_level, system_instruction, response_schema,
                    output_tokens):
    #  Nemotron does not follow json format, so the schema goes in the prompt and Pydantic checks 
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
    choices = get_value(response, "choices", []) or []
    if not choices:
        raise BadAnswer("the AI provider returned an empty answer")
    choice = choices[0]
    message = get_value(choice, "message")
    return {"text": get_value(message, "content", "") or "", "finish_reason": get_value(choice, "finish_reason")}


# Makes sure a model can be used with these settings: it has an API key, and the reasoning
def check_model(model_name, reasoning, output_tokens):
    model = AI_MODELS[model_name]
    if model["client"] is None or not model["model"]:
        raise ValueError(f"{model_name} is not configured.")
    capability = MODEL_CAPABILITIES.get(model["model"])
    if capability is None or reasoning not in capability["levels"]:
        raise ValueError(f"{model_name} has no verified {reasoning} reasoning configuration.")
    if output_tokens > capability["output_limit"]:
        raise ValueError(f"{model_name} cannot return {output_tokens} output tokens.")


# Sends a prompt to the model's AI provider and returns the answer text.
# Raises BadAnswer when the answer was cut off,out of tokens or blocked
def ask_model(model_name, prompt, reasoning, instructions, schema, output_tokens):
    model = AI_MODELS[model_name]
    if model["provider"] == "gemini":
        result = call_gemini(model, prompt, reasoning, instructions, schema, output_tokens)
    elif model["provider"] == "groq":
        result = call_groq(model, prompt, reasoning, instructions, schema, output_tokens)
    elif model["provider"] == "openrouter":
        result = call_openrouter(model, prompt, reasoning, instructions, schema, output_tokens)
    else:
        raise ValueError(f"Unsupported AI provider: {model['provider']}")

    if result["finish_reason"] not in {"stop", "STOP", "FinishReason.STOP"}:
        raise BadAnswer("the AI answer was cut off before it finished")
    return result["text"]

