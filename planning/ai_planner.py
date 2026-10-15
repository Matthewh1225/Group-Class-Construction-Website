import json
import os
from time import monotonic

from google import genai
from groq import Groq
from openrouter import OpenRouter

from .ai_config import (
    AI_TIMEOUT,
    PLANNER_PROMPT,
    MODEL_CAPABILITIES,
    STRONG_MODEL_OVERRIDE,
    WORKFLOW_MODEL_KEYS,
)


def make_gemini_client(key_name):
    api_key = os.getenv(key_name)
    if api_key:
        return genai.Client(api_key=api_key)
    return None


gemini_client_1 = make_gemini_client("GEMINI_API_KEY")
gemini_client_2 = make_gemini_client("GEMINI_API_KEY2")

groq_key = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=groq_key) if groq_key else None

openrouter_key = os.getenv("OPENROUTER_API_KEY")
openrouter_client = OpenRouter(api_key=openrouter_key) if openrouter_key else None

AI_MODELS = {
    "gemini_strong": {
        "provider": "gemini",
        "client": gemini_client_1,
        "model": STRONG_MODEL_OVERRIDE or os.getenv("gemini_model_strong"),
    },
    "gemini_weak": {
        "provider": "gemini",
        "client": gemini_client_2,
        "model": os.getenv("gemini_model_fast"),
    },
    "groq": {
        "provider": "groq",
        "client": groq_client,
        "model": os.getenv("GROQ_gpt-oss", "openai/gpt-oss-120b"),
    },
    "openrouter": {
        "provider": "openrouter",
        "client": openrouter_client,
        "model": os.getenv("OPENROUTER_nemotron-3"),
    },
}


def get_value(item, name, default=None):
    """Read a value from either an SDK object or a dictionary."""
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def make_messages(system_instruction, prompt):
    return [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": prompt},
    ]


# a schema tells the AI which JSON fields and types to return
def make_response_format(response_schema):
    if response_schema is None:
        return None
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "materials_plan",
            "strict": True,
            "schema": response_schema,
        },
    }


def call_gemini(model, prompt, thinking_level, system_instruction, response_schema,
                output_tokens=8192):
    config = {
        "system_instruction": system_instruction,
        "thinking_config": {"thinking_level": thinking_level},
        "max_output_tokens": output_tokens,
        "http_options": {"timeout": AI_TIMEOUT * 1000, "retry_options": {"attempts": 1}},
        "automatic_function_calling": {"disable": True},
    }
    if response_schema is not None:
        config["response_mime_type"] = "application/json"
        config["response_json_schema"] = response_schema

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
    # use the same result keys even though each provider responds differently
    return response, {
        "text": get_value(response, "text", "") or "",
        "status": "completed",
        "thinking_tokens": get_value(usage, "thoughts_token_count"),
        "input_tokens": get_value(usage, "prompt_token_count"),
        "output_tokens": get_value(usage, "candidates_token_count"),
        "total_tokens": get_value(usage, "total_token_count"),
        "finish_reason": finish_reason,
        "resolved_model_version": get_value(response, "model_version"),
    }


def call_groq(model, prompt, thinking_level, system_instruction, response_schema,
              output_tokens=8192):
    if response_schema is not None:
        # Groq can reject a full estimate during constrained generation with HTTP 400.
        # JSON object mode still gives parseable JSON; Pydantic and Python check it below.
        prompt += "\nReturn one JSON object matching this schema:\n" + json.dumps(response_schema)
    response_format = {"type": "json_object"} if response_schema is not None else {"type": "text"}
    response = model["client"].with_options(max_retries=0).chat.completions.create(
        model=model["model"],
        messages=make_messages(system_instruction, prompt),
        temperature=0.5,
        max_completion_tokens=output_tokens,
        reasoning_effort=thinking_level,
        response_format=response_format,
        timeout=AI_TIMEOUT,
    )
    usage = response.usage
    return response, {
        "text": response.choices[0].message.content or "",
        "status": "completed",
        "thinking_tokens": get_value(get_value(usage, "completion_tokens_details"), "reasoning_tokens"),
        "input_tokens": get_value(usage, "prompt_tokens"),
        "output_tokens": get_value(usage, "completion_tokens"),
        "total_tokens": get_value(usage, "total_tokens"),
        "finish_reason": get_value(response.choices[0], "finish_reason"),
    }


def call_openrouter(model, prompt, thinking_level, system_instruction, response_schema,
                    output_tokens=8192):
    capability = MODEL_CAPABILITIES.get(model["model"], {})
    if capability.get("structured_output") == "prompt_json_validated" and response_schema:
        # This model does not advertise constrained JSON. Validate its JSON locally.
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
    response_format = make_response_format(response_schema)
    if response_format is not None and capability.get("structured_output") != "prompt_json_validated":
        options["response_format"] = response_format

    # **options passes each dictionary entry as a named argument
    response = model["client"].chat.send(**options)
    usage = get_value(response, "usage")
    message = get_value(get_value(response, "choices", [])[0], "message")
    return response, {
        "text": get_value(message, "content", "") or "",
        "status": "completed",
        "thinking_tokens": get_value(get_value(usage, "completion_tokens_details"), "reasoning_tokens"),
        "input_tokens": get_value(usage, "prompt_tokens"),
        "output_tokens": get_value(usage, "completion_tokens"),
        "total_tokens": get_value(usage, "total_tokens"),
        "finish_reason": get_value(get_value(response, "choices", [])[0], "finish_reason"),
    }


def get_ai_response(
    model_name,
    prompt,
    thinking_level="low",
    system_instruction=PLANNER_PROMPT,
    response_schema=None,
    output_tokens=8192,
):
    if model_name not in AI_MODELS:
        raise ValueError(f"Unknown AI model: {model_name}")

    model = AI_MODELS[model_name]
    if model["client"] is None:
        raise ValueError(f"The API key for {model_name} is not configured.")
    if not model["model"]:
        raise ValueError(f"The model name for {model_name} is not configured.")

    provider = model["provider"]
    # monotonic measures elapsed time even if the system clock changes
    started_at = monotonic()

    if provider == "gemini":
        response, result = call_gemini(
            model, prompt, thinking_level, system_instruction, response_schema, output_tokens
        )
    elif provider == "groq":
        response, result = call_groq(
            model, prompt, thinking_level, system_instruction, response_schema, output_tokens
        )
    elif provider == "openrouter":
        response, result = call_openrouter(
            model, prompt, thinking_level, system_instruction, response_schema, output_tokens
        )
    else:
        raise ValueError(f"Unsupported AI provider: {provider}")

    result["provider"] = provider
    result["id"] = get_value(response, "id")
    result["model"] = get_value(response, "model", model["model"])
    result["thinking_level"] = thinking_level
    result["elapsed_seconds"] = round(monotonic() - started_at, 2)
    return result


def workflow_model(model_name, reasoning):
    model_key = WORKFLOW_MODEL_KEYS[model_name]
    model = AI_MODELS[model_key]
    if model["client"] is None or not model["model"]:
        raise ValueError(f"{model_name} is not configured.")
    capability = MODEL_CAPABILITIES.get(model["model"])
    if capability is None or reasoning not in capability["levels"]:
        raise ValueError(f"{model_name} has no verified {reasoning} reasoning configuration.")
    return model, capability


def workflow_response(model_name, prompt, reasoning, instructions, schema, output_tokens):
    model, capability = workflow_model(model_name, reasoning)
    model_key = WORKFLOW_MODEL_KEYS[model_name]
    if output_tokens > capability["output_limit"]:
        raise ValueError("The requested output size exceeds this model's documented limit.")
    result = get_ai_response(
        model_key, prompt, thinking_level=reasoning,
        system_instruction=instructions, response_schema=schema,
        output_tokens=output_tokens,
    )
    result["requested_reasoning"] = reasoning
    result["transmitted_reasoning"] = {capability["setting"]: reasoning}
    result["requested_model"] = model["model"]
    result["structured_output_mode"] = capability["structured_output"]
    # An accepted setting is evidence of the request, not of internal computation.
    finish = result.get("finish_reason")
    if finish not in {"stop", "STOP", "FinishReason.STOP"}:
        result["status"] = "incomplete"
    return result


def response_metadata(response):
    # copy first so removing fields does not change the original response
    metadata = response.copy()
    metadata.pop("text", None)
    metadata.pop("plan", None)
    metadata.pop("steps", None)
    metadata.pop("project", None)
    return metadata

