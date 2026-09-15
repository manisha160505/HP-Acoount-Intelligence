import json
import logging
from openai import OpenAI
from app.config.settings import settings

logger = logging.getLogger(__name__)

def get_openai_client() -> OpenAI | None:
    api_key = settings.OPENAI_API_KEY.strip()
    if not api_key:
        logger.warning("OPENAI_API_KEY is not set in environment or settings.")
        return None
    
    endpoint = settings.OPENAI_ENDPOINT.strip()
    return OpenAI(base_url=endpoint, api_key=api_key)

def generate_chat_completion(system_prompt: str, messages: list,
                             temperature: float = 0.3) -> str | None:
    """A multi-turn text completion. Returns prose, not JSON.

    Strategy Chat needs the conversation itself in the request - a seller asks
    "how does that compare to last year" and the model has to see what "that"
    referred to. Flattening the history into one user string loses the turn
    boundaries the model uses to do that.

    `messages` is [{"role": "user"|"assistant", "content": str}]; anything else
    is dropped rather than sent, so a malformed history cannot become a prompt
    injection vector. The system prompt is always first and always ours.

    Runs on OPENAI_MODEL_NAME (gpt-4o), not the retrieval model: index building
    stays on the slower model, but answering happens while a seller waits.

    The model writes the prose and has no authority over any fact in it -
    everything it says is validated against retrieved evidence afterwards.
    """
    client = get_openai_client()
    if not client:
        logger.warning("Cannot generate completion: OpenAI client is uninitialized.")
        return None

    turns = [{"role": "system", "content": system_prompt}]
    for message in (messages or []):
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip().lower()
        content = str(message.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            turns.append({"role": role, "content": content})

    if len(turns) == 1:
        logger.warning("Cannot generate completion: no usable messages supplied.")
        return None

    model_name = settings.OPENAI_MODEL_NAME or "gpt-4o"
    try:
        response = client.chat.completions.create(
            model=model_name, messages=turns, temperature=temperature)
        return (response.choices[0].message.content or "").strip() or None
    except Exception as exc:
        logger.error("Error calling chat completion: %s", exc)
        return None


def generate_gpt4o_json_completion(system_prompt: str, user_prompt: str) -> dict | None:
    client = get_openai_client()
    if not client:
        logger.warning("Cannot generate completion: OpenAI client is uninitialized.")
        return None

    model_name = settings.OPENAI_MODEL_NAME or "gpt-4o"
    try:
        response = client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2
        )
        content = response.choices[0].message.content
        if content:
            return json.loads(content)
        return None
    except Exception as e:
        logger.error(f"Error calling GPT-4o API completion: {e}")
        return None
