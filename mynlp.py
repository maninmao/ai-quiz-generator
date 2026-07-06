import os
import re
import json
import random
from google import genai
from dotenv import load_dotenv


load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = """I want you to generate multiple-choice quiz questions from the extracted text from a pdf notes. Output ONLY a JSON array. No explanations, no markdown, no code fences.

Sample Quiz FORMAT :
[
  {"type": "fill_blank", "question": "Fill in the blank: The process of _____ converts light energy into chemical energy.", "options": ["photosynthesis", "respiration", "digestion", "fermentation"], "answer": "photosynthesis"},
  {"type": "true_false", "question": "True or False: Plants absorb carbon dioxide during photosynthesis.", "options": ["True", "False"], "answer": "True"}
]

RULES:
1. Every question must be answerable using ONLY the text given. No outside knowledge.
2. fill_blank: real sentence from the text, one key term replaced with "_____", 4 options total (1 correct + 3 plausible distractors). "answer" must match one option exactly.
3. true_false: a fact from the text, either accurate ("True") or altered ("False"). Options always ["True", "False"].
4. About 70% fill_blank, 30% true_false.
5. No questions about titles, headers, or the document itself.
6. Strictly valid JSON: escape quotes properly, no trailing commas, no line breaks inside strings.
"""



def _extract_json(raw_text):
    raw_text = raw_text.strip()
    match = re.search(r"\[.*\]", raw_text, re.DOTALL)
    if match:
        raw_text = match.group(0)

    raw_text = re.sub(r',\s*([\]}])', r'\1', raw_text)

    try:
        return json.loads(raw_text)
        
    except json.JSONDecodeError:
        
        print("=== JSON PARSE FAILED, RAW TEXT ===")
        print(raw_text)
        print("=== END ===")
        raise
def _parse_with_repair(raw_text):
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        # Truncated mid-array — salvage complete objects only
        last_complete = raw_text.rfind("},")
        if last_complete != -1:
            salvage = raw_text[:last_complete + 1] + "]"
            try:
                return json.loads(salvage)
            except json.JSONDecodeError:
                pass
        print("=== JSON PARSE FAILED, RAW TEXT ===")
        print(raw_text)
        print("=== END ===")
        return []

def generate_questions(text, num_questions=10):
    max_chars = 12000
    if len(text) > max_chars:
        text = text[:max_chars]

    user_prompt = f"Generate exactly {num_questions} questions from this text.\n\nTEXT:\n{text}"

    schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "type": {"type": "STRING", "enum": ["fill_blank", "true_false"]},
                "question": {"type": "STRING"},
                "options": {"type": "ARRAY", "items": {"type": "STRING"}},
                "answer": {"type": "STRING"},
            },
            "required": ["type", "question", "options", "answer"],
        },
    }

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=user_prompt,
            config={
                "system_instruction": SYSTEM_PROMPT,
                "temperature": 0.3,
                "max_output_tokens": 6000,
                "response_mime_type": "application/json",
                "response_schema": schema,
                "thinking_config": {"thinking_budget": 0},
            },
            # config={
            #     "system_instruction": SYSTEM_PROMPT,
            #     "temperature": 0.3,
            #     "max_output_tokens": 2500,
            #     "response_mime_type": "application/json",
            #     "response_schema": schema,
            # },
        )
        # questions = json.loads(response.text)
        questions = _parse_with_repair(response.text)
    except Exception as e:
        print(f"[generate_questions] Gemini error: {e}")
        return []

    valid = []
    for q in questions:
        if (
            isinstance(q, dict)
            and q.get("question")
            and isinstance(q.get("options"), list)
            and len(q["options"]) >= 2
            and q.get("answer") in q["options"]
        ):
            valid.append(q)

    random.shuffle(valid)
    for i, q in enumerate(valid):
        q["id"] = i

    return valid[:num_questions]