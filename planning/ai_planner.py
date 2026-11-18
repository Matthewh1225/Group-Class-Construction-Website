import json
import logging
import os

import httpx
from google import genai
from groq import BadRequestError, Groq

from .ai_config import AI_TIMEOUT, MODELS
from .schemas import AnswerFormatError, PlanningError

# Gemini and Groq retry a temporary failure once in their SDKs; the workflow retries a bad answer once.
# Gemini 429s are not retried: resending a big request only fails again, so the next fallback runs right away.
GEMINI_RETRY_OPTIONS = {"attempts": 2, "initial_delay": 5, "max_delay": 30,  # 2 tries in total
                        "http_status_codes": [408, 500, 502, 503, 504]}
GROQ_MAX_RETRIES = 1  # 2 tries in total

logger = logging.getLogger(__name__)


def make_client(provider, key_name, fallback_key_name=None):
    api_key = os.getenv(key_name) or (os.getenv(fallback_key_name) if fallback_key_name else None)
    if not api_key:
        return None
    if provider == "gemini":
        return genai.Client(api_key=api_key)
    if provider == "groq":
        return Groq(api_key=api_key)
    if provider == "cloudflare":
        return {"token": api_key, "account_id": os.getenv("CLOUDFLARE_ACCOUNT_ID")}
    if provider == "openrouter":
        return {"token": api_key}
    raise ValueError(f"Unsupported AI provider: {provider}")


AI_MODELS = {}
for model_name, settings in MODELS.items():
    AI_MODELS[model_name] = {
        "provider": settings["provider"],
        "client": make_client(settings["provider"], settings["api_key"], settings.get("fallback_api_key")),
        "model": os.getenv(settings["model_env"]) or settings["default"],
        "enforces_schema": settings.get("enforces_schema", True),
        "timeout": settings.get("timeout", AI_TIMEOUT),
    }


def make_messages(system_instruction, prompt):
    return [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": prompt},
    ]


def json_schema_format(response_schema):
    """Build the shared JSON response format; Gemini takes the schema directly."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": response_schema["title"],
            "strict": True,
            "schema": response_schema,
        },
    }


def call_gemini(model, prompt, thinking_level, system_instruction, response_schema, output_tokens):
    config = {
        "system_instruction": system_instruction,
        "thinking_config": {"thinking_level": thinking_level},
        "max_output_tokens": output_tokens,
        "http_options": {"timeout": model["timeout"] * 1000, "retry_options": GEMINI_RETRY_OPTIONS},
        "automatic_function_calling": {"disable": True},
        "response_mime_type": "application/json",
        "response_json_schema": response_schema,
    }

    response = model["client"].models.generate_content(
        model=model["model"],
        contents=prompt,
        config=config,
    )
    # A blocked prompt may have no answer.
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
    try:
        response = model["client"].with_options(max_retries=GROQ_MAX_RETRIES).chat.completions.create(
            model=model["model"],
            messages=make_messages(system_instruction, prompt),
            temperature=0.5,
            max_completion_tokens=output_tokens,
            reasoning_effort=thinking_level,
            response_format=json_schema_format(response_schema),
            timeout=AI_TIMEOUT,
        )
    except BadRequestError as error:
        if "json_validate_failed" in str(error.body):
            raise AnswerFormatError("the provider rejected the generated answer because it did not match the required JSON format") from error
        raise
    if not response.choices:
        raise PlanningError("the AI provider returned an empty answer")
    choice = response.choices[0]
    return {"text": choice.message.content or "", "finish_reason": choice.finish_reason}


def call_cloudflare(model, prompt, thinking_level, system_instruction, response_schema, output_tokens):
    options = {
        "messages": make_messages(system_instruction, prompt),
        "max_completion_tokens": output_tokens,
        # Require True so a string like "low" cannot accidentally enable thinking.
        "chat_template_kwargs": {"enable_thinking": thinking_level is True},
        "response_format": json_schema_format(response_schema),
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


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def openrouter_reasoning(thinking_level):
    """A number is a thinking budget in tokens; True turns thinking on with the model's default."""
    if thinking_level is True:
        return {"enabled": True}
    if isinstance(thinking_level, int) and thinking_level > 0:
        return {"max_tokens": thinking_level}
    raise ValueError(f"OpenRouter reasoning must be True or a token budget, not {thinking_level!r}")


def remove_code_fence(text):
    """Models that are not forced to return JSON sometimes wrap it in ```json ... ```."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def call_openrouter(model, prompt, thinking_level, system_instruction, response_schema, output_tokens):
    options = {
        "model": model["model"],
        "max_tokens": output_tokens,
        "reasoning": openrouter_reasoning(thinking_level),
        "stream": False,
    }
    if model["enforces_schema"]:
        options["response_format"] = json_schema_format(response_schema)
    else:
        system_instruction = (system_instruction
                              + "\nReturn only one JSON object, with no other text, that matches this JSON Schema:\n"
                              + json.dumps(response_schema))
    options["messages"] = make_messages(system_instruction, prompt)

    response = httpx.post(
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {model['client']['token']}"},
        json=options,
        timeout=AI_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    # OpenRouter can report a provider error inside a normal 200 response.
    if data.get("error"):
        raise PlanningError("OpenRouter reported an error instead of an answer")
    choices = data.get("choices") or []
    if not choices:
        raise PlanningError("OpenRouter returned no answer")
    choice = choices[0]
    message = choice.get("message") or {}
    if message.get("refusal"):
        raise PlanningError("the model refused to answer this request")
    text = message.get("content") or ""
    if not model["enforces_schema"]:
        text = remove_code_fence(text)
    return {"text": text, "finish_reason": choice.get("finish_reason")}


def ask_model(model_name, prompt, reasoning, instructions, schema, output_tokens):
    model = AI_MODELS[model_name]
    if model["client"] is None:
        raise PlanningError(f"The {model_name} AI model is not configured.")
    if model["provider"] == "gemini":
        result = call_gemini(model, prompt, reasoning, instructions, schema, output_tokens)
    elif model["provider"] == "groq":
        result = call_groq(model, prompt, reasoning, instructions, schema, output_tokens)
    elif model["provider"] == "cloudflare":
        result = call_cloudflare(model, prompt, reasoning, instructions, schema, output_tokens)
    elif model["provider"] == "openrouter":
        result = call_openrouter(model, prompt, reasoning, instructions, schema, output_tokens)
    else:
        raise PlanningError(f"Unsupported AI provider: {model['provider']}")
    # Gemini returns an enum; the other providers return strings.
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
        raise AnswerFormatError("the provider reported completion but returned no text answer")
    return result["text"]

