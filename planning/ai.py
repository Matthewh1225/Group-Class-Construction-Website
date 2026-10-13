import json
import os
from time import monotonic

from cloudflare import Cloudflare
from google import genai
from groq import Groq
from openrouter import OpenRouter

from .ai_config import (
    AI_TIMEOUT,
    DRAFT_INSTRUCTIONS,
    DRAFT_STRUCTURE,
    PLAN_SETTINGS,
    PROJECT_STRUCTURE,
    REVIEW_INSTRUCTIONS,
)


def make_gemini_client(key_name):
    api_key = os.getenv(key_name)
    if api_key:
        return genai.Client(api_key=api_key)
    return None


gemini_client_1 = make_gemini_client("GEMINI_API_KEY")
gemini_client_2 = make_gemini_client("GEMINI_API_KEY2")
gemini_client_3 = make_gemini_client("GEMINI_API_KEY3")
gemini_client_4 = make_gemini_client("GEMINI_API_KEY4")

groq_key = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=groq_key)

openrouter_key = os.getenv("OPENROUTER_API_KEY")
openrouter_client = OpenRouter(api_key=openrouter_key)

cloudflare_key = os.getenv("CLOUDFLARE_API_KEY")
cloudflare_client = Cloudflare(api_token=cloudflare_key)


AI_MODELS = {
    "gemini_strong": {
        "provider": "gemini",
        "client": gemini_client_1,
        "model": os.getenv("GEMINI_MODEL"),
    },
    "gemini_strong_2": {
        "provider": "gemini",
        "client": gemini_client_3,
        "model": os.getenv("GEMINI_MODEL"),
    },
    "gemini_strong_3": {
        "provider": "gemini",
        "client": gemini_client_4,
        "model": os.getenv("GEMINI_MODEL"),
    },
    "gemini_weak": {
        "provider": "gemini",
        "client": gemini_client_2,
        "model": os.getenv("GEMINI_MODEL2"),
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
    "cloudflare": {
        "provider": "cloudflare",
        "client": cloudflare_client,
        "model": os.getenv("CLOUDFLARE_glm-4.7-flash"),
    },
    "cloudflare_2": {
        "provider": "cloudflare",
        "client": cloudflare_client,
        "model": os.getenv("CLOUDFLARE_gemma-4"),
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


def call_gemini(model, prompt, thinking_level, system_instruction, response_schema):
    config = {
        "system_instruction": system_instruction,
        "thinking_config": {"thinking_level": thinking_level},
    }
    if response_schema is not None:
        config["response_format"] = {
            "type": "text",
            "mime_type": "application/json",
            "schema": response_schema,
        }

    response = model["client"].models.generate_content(
        model=model["model"],
        contents=prompt,
        config=config,
    )
    usage = get_value(response, "usage_metadata")
    return response, {
        "text": get_value(response, "text", "") or "",
        "status": "completed",
        "thinking_tokens": get_value(usage, "thoughts_token_count"),
        "input_tokens": get_value(usage, "prompt_token_count"),
        "output_tokens": get_value(usage, "candidates_token_count"),
        "total_tokens": get_value(usage, "total_token_count"),
    }


def call_groq(model, prompt, thinking_level, system_instruction, response_schema):
    response_format = make_response_format(response_schema) or {"type": "text"}
    response = model["client"].chat.completions.create(
        model=model["model"],
        messages=make_messages(system_instruction, prompt),
        temperature=0.5,
        max_completion_tokens=8192,
        reasoning_effort=thinking_level,
        response_format=response_format,
        timeout=AI_TIMEOUT,
    )
    usage = response.usage
    return response, {
        "text": response.choices[0].message.content or "",
        "status": "completed",
        "thinking_tokens": None,
        "input_tokens": get_value(usage, "prompt_tokens"),
        "output_tokens": get_value(usage, "completion_tokens"),
        "total_tokens": get_value(usage, "total_tokens"),
    }


def call_openrouter(model, prompt, thinking_level, system_instruction, response_schema):
    options = {
        "model": model["model"],
        "messages": make_messages(system_instruction, prompt),
        "reasoning_effort": thinking_level,
        "stream": False,
    }
    response_format = make_response_format(response_schema)
    if response_format is not None:
        options["response_format"] = response_format

    response = model["client"].chat.send(**options)
    usage = get_value(response, "usage")
    message = get_value(get_value(response, "choices", [])[0], "message")
    return response, {
        "text": get_value(message, "content", "") or "",
        "status": "completed",
        "thinking_tokens": get_value(usage, "reasoning_tokens"),
        "input_tokens": get_value(usage, "prompt_tokens"),
        "output_tokens": get_value(usage, "completion_tokens"),
        "total_tokens": get_value(usage, "total_tokens"),
    }


def call_cloudflare(model, prompt, thinking_level, system_instruction, response_schema):
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    if not account_id:
        raise ValueError("CLOUDFLARE_ACCOUNT_ID is not configured.")

    options = {
        "model_name": model["model"],
        "account_id": account_id,
        "messages": make_messages(system_instruction, prompt),
    }
    if response_schema is not None:
        options["response_format"] = {
            "type": "json_schema",
            "json_schema": response_schema,
        }

    response = model["client"].ai.run(**options)
    output = get_value(response, "response", "")
    if isinstance(output, (dict, list)):
        output = json.dumps(output)
    usage = get_value(response, "usage")
    return response, {
        "text": output or "",
        "status": "completed",
        "thinking_tokens": None,
        "input_tokens": get_value(usage, "prompt_tokens"),
        "output_tokens": get_value(usage, "completion_tokens"),
        "total_tokens": get_value(usage, "total_tokens"),
    }


def get_ai_response(
    model_name,
    prompt,
    thinking_level="low",
    system_instruction=DRAFT_INSTRUCTIONS,
    response_schema=None,
):
    if model_name not in AI_MODELS:
        raise ValueError(f"Unknown AI model: {model_name}")

    model = AI_MODELS[model_name]
    if model["client"] is None:
        raise ValueError(f"The API key for {model_name} is not configured.")
    if not model["model"]:
        raise ValueError(f"The model name for {model_name} is not configured.")

    provider = model["provider"]
    started_at = monotonic()

    if provider == "gemini":
        response, result = call_gemini(
            model, prompt, thinking_level, system_instruction, response_schema
        )
    elif provider == "groq":
        response, result = call_groq(
            model, prompt, thinking_level, system_instruction, response_schema
        )
    elif provider == "openrouter":
        response, result = call_openrouter(
            model, prompt, thinking_level, system_instruction, response_schema
        )
    elif provider == "cloudflare":
        response, result = call_cloudflare(
            model, prompt, thinking_level, system_instruction, response_schema
        )
    else:
        raise ValueError(f"Unsupported AI provider: {provider}")

    result["provider"] = provider
    result["id"] = get_value(response, "id")
    result["model"] = get_value(response, "model", model["model"])
    result["thinking_level"] = thinking_level
    result["elapsed_seconds"] = round(monotonic() - started_at, 2)
    return result


def response_metadata(response):
    metadata = response.copy()
    metadata.pop("text", None)
    metadata.pop("plan", None)
    metadata.pop("steps", None)
    metadata.pop("project", None)
    return metadata


def plan_project(project_data, plan_type="basic"):
    settings = PLAN_SETTINGS.get(plan_type)
    if settings is None:
        raise ValueError("Choose either a basic or pro plan.")

    is_pro_plan = settings["requires_review"]
    response_schema = DRAFT_STRUCTURE if is_pro_plan else PROJECT_STRUCTURE
    draft = get_ai_response(
        settings["draft_model"],
        json.dumps(project_data, indent=2),
        thinking_level=settings["draft_reasoning"],
        system_instruction=DRAFT_INSTRUCTIONS,
        response_schema=response_schema,
    )

    draft["steps"] = [response_metadata(draft)]
    draft["plan_type"] = plan_type
    draft["plan"] = json.loads(draft["text"])

    if is_pro_plan:
        draft["text"] = json.dumps(draft["plan"], indent=2)
        draft["project"] = project_data
    return draft


def review_plan(draft, answers):
    settings = PLAN_SETTINGS["pro"]
    questions = draft["plan"]["questions"]

    clarifications = []
    for question, answer in zip(questions, answers):
        clarifications.append({"question": question, "answer": answer.strip()})

    review_data = {
        "project": draft["project"],
        "draft": draft["plan"],
        "clarifications": clarifications,
    }
    result = get_ai_response(
        settings["review_model"],
        json.dumps(review_data, indent=2),
        thinking_level=settings["review_reasoning"],
        system_instruction=REVIEW_INSTRUCTIONS,
        response_schema=PROJECT_STRUCTURE,
    )

    result["plan"] = json.loads(result["text"])
    result["steps"] = draft["steps"] + [response_metadata(result)]
    result["plan_type"] = "pro"
    result["elapsed_seconds"] = round(
        draft["elapsed_seconds"] + result["elapsed_seconds"], 2
    )
    return result
