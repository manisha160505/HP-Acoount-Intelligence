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
