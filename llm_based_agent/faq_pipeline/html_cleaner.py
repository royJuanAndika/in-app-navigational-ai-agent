import re

def clean_html(raw: str) -> str:
    """
    Clean HTML content by stripping tags, removing images, and collapsing whitespace.
    
    Tasks:
    - Strip all HTML tags
    - Remove inline <img ...> tags entirely
    - Collapse multiple whitespace/newlines to single newlines
    - Strip leading/trailing whitespace
    """
    if not raw:
        return ""

    # 1. Remove inline <img ...> tags entirely (including those with content if any, though img is self-closing)
    # Using a regex to find <img> tags
    cleaned = re.sub(r'<img[^>]*>', '', raw)

    # 2. Strip all HTML tags, replacing with space to prevent mashing text
    # This regex matches anything between < and >
    cleaned = re.sub(r'<[^>]+>', ' ', cleaned)

    # 3. Collapse multiple whitespace/newlines to single newlines
    # First, replace multiple whitespaces (excluding newlines) with a single space
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    # Then, replace multiple newlines with a single newline
    cleaned = re.sub(r'\n+', '\n', cleaned)
    # Ensure we don't have spaces at the start/end of lines if there are multiple lines
    cleaned = '\n'.join(line.strip() for line in cleaned.split('\n'))
    # Collapse multiple newlines again after stripping line ends
    cleaned = re.sub(r'\n+', '\n', cleaned)

    # 4. Strip leading/trailing whitespace from the entire string
    return cleaned.strip()
