#!/usr/bin/env python3
import json

with open("data/nkg_chunked_output/customer_employee.dryrun.json") as f:
    data = json.load(f)

print("=" * 80)
print("DRY-RUN INSPECTION: customer_employee.html")
print("=" * 80)
print(f"\nPage: {data['meta']['page_url']}")
print(f"Title: {data['meta']['page_title']}")
print(f"Total chunks: {data['meta']['chunk_config']['total_chunks']}")
print(f"Total DOM ids: {data['dom_info']['total_dom_ids']}")
print(f"\nDOM ids (first 20): {data['dom_info']['all_dom_ids'][:20]}")

print("\n" + "=" * 80)
print("CHUNK 1 PROMPT STRUCTURE")
print("=" * 80)

prompt = data['prompts'][0]['user_prompt']
print(f"\nPrompt length: {len(prompt)} chars")
print(f"Chunk lines: {data['prompts'][0]['line_range']}")
print(f"Chunk HTML size: {data['prompts'][0]['char_count']} chars")
print("\nFIRST 1500 CHARS OF PROMPT:")
print("-" * 80)
print(prompt[:1500])
print("-" * 80)
print("\n[... middle content omitted ...]")
print("\nLAST 500 CHARS OF PROMPT:")
print("-" * 80)
print(prompt[-500:])
print("-" * 80)
