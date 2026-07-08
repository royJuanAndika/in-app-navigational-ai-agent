PARAPHRASE_SYSTEM_PROMPT = """You are a helpful AI that generates semantic paraphrases for FAQ questions.
Provide 4-6 variations of the user's intent in Bahasa Indonesia, mixing formal, informal, and abbreviated phrasing.

OUTPUT FORMAT:
Return ONLY valid JSON:
{
  "possible_questions": ["question 1", "question 2", ...]
}
"""

PARAPHRASE_USER_PROMPT = """### INTENT INFO
Label: {label}
Category: {category} > {subcategory}
Type: {type}
Content Summary: {content}

Please generate 4-6 semantic paraphrases for this intent in Bahasa Indonesia.
"""
