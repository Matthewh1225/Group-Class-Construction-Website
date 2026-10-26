import json
import logging
import os

import httpx
from google import genai
from groq import BadRequestError, Groq
from openrouter import OpenRouter

from .ai_config import AI_TIMEOUT, MODELS
from .schemas import PlanningError

logger = logging.getLogger(__name__)


def make_client(provider, key_name):
    api_key = os.getenv(key_name)
    if not api_key:
        return None
    if provider == "gemini":
        return genai.Client(api_key=api_key)
    if provider == "groq":
        return Groq(api_key=api_key)
    if provider == "cloudflare":
        return {"token": api_key, "account_id": os.getenv("CLOUDFLARE_ACCOUNT_ID")}
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


def call_gemini(model, prompt, thinking_level, system_instruction, response_schema, output_tokens):
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
    # A blocked prompt may have feedback but no answer candidates.
    if not response.candidates:
        feedback = response.prompt_feedback
        if feedback and feedback.block_reason:
            reason = feedback.block_reason.value
            raise PlanningError(f"the provider blocked the prompt (reason: {reason})")
        raise PlanningError("the provider returned no answer candidates")
    finish_reason = response.candidates[0].finish_reason
    return {"text": response.text or "", "finish_reason": finish_reason}


def call_groq(model, prompt, thinking_level, system_instruction, response_schema,
              output_tokens):
    prompt += "\nReturn only one JSON object matching this schema:\n" + json.dumps(response_schema)
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
            raise PlanningError("the provider rejected the generated answer because it did not match the required JSON format") from error
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
    if isinstance(choice.message.refusal, str) and choice.message.refusal.strip():
        raise PlanningError("the model refused to answer this request")
    return {"text": choice.message.content or "", "finish_reason": choice.finish_reason}


def call_cloudflare(model, prompt, thinking_level, system_instruction, response_schema, output_tokens):
    options = {
        "messages": make_messages(system_instruction, prompt),
        "max_completion_tokens": output_tokens,
        # GLM uses a boolean instead of low, medium or high.
        "chat_template_kwargs": {"enable_thinking": thinking_level},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": response_schema["title"],
                "strict": True,
                "schema": response_schema,
            },
        },
        "stream": False,
    }

    account_id = model["client"]["account_id"]
    if not account_id:
        raise PlanningError("Cloudflare is missing CLOUDFLARE_ACCOUNT_ID in the environment")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model['model']}"
    response = httpx.post(
        url,
        headers={"Authorization": f"Bearer {model['client']['token']}"},
        json=options,
        timeout=AI_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("success") is False or data.get("error") or data.get("errors"):
        raise PlanningError("Cloudflare reported an error instead of a matching result")
    result = data.get("result") or {}
    choices = result.get("choices", [])
    if not choices:
        raise PlanningError("Cloudflare returned no matching answer")
    choice = choices[0]
    message = choice["message"]
    if message.get("refusal"):
        raise PlanningError("the model refused to answer this request")
    return {"text": message.get("content") or "", "finish_reason": choice.get("finish_reason")}


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
    elif model["provider"] == "cloudflare":
        result = call_cloudflare(model, prompt, reasoning, instructions, schema, output_tokens)
    else:
        raise PlanningError(f"Unsupported AI provider: {model['provider']}")
    # Gemini returns an enum; Groq and OpenRouter return strings.
    reason = getattr(result["finish_reason"], "value", result["finish_reason"])
    logger.info("AI response: provider=%s model=%s finish_reason=%s",
                model["provider"], model["model"], reason)
    if reason in ("length", "MAX_TOKENS"):
        raise PlanningError(
            f"the model reached its output token limit (requested limit: {output_tokens:,}; "
            f"finish reason: {reason}). Try a smaller project or increase this stage's output allowance"
        )
    if reason in ("content_filter", "SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII",
                  "IMAGE_SAFETY", "IMAGE_PROHIBITED_CONTENT"):
        raise PlanningError(f"the provider blocked the answer (finish reason: {reason}). Review the project description")
    if reason in ("RECITATION", "IMAGE_RECITATION"):
        raise PlanningError(f"the provider stopped the answer because of its recitation filter (finish reason: {reason})")
    if reason in ("tool_calls", "function_call", "MALFORMED_FUNCTION_CALL", "UNEXPECTED_TOOL_CALL", "TOO_MANY_TOOL_CALLS"):
        raise PlanningError(f"the model attempted a tool call instead of returning the requested JSON (finish reason: {reason})")
    if reason == "error":
        raise PlanningError("the provider reported an error while generating the answer (finish reason: error). Try again later")
    if reason in (None, "", "FINISH_REASON_UNSPECIFIED"):
        raise PlanningError("the provider did not report a completion reason, so the answer could not be accepted")
    if reason not in ("stop", "STOP"):
        raise PlanningError(f"the provider stopped the answer for an unexpected reason ({reason})")
    if not isinstance(result["text"], str) or not result["text"].strip():
        raise PlanningError("the provider reported completion but returned no text answer")
    return result["text"]

