# Generation input contracts

The agent writes these files after reviewing extracted evidence, asking necessary questions, and performing current research. The deterministic CLI validates every identifier before generating a candidate.

## `research.json`

```json
{
  "sources": [
    {
      "id": "WEB-001",
      "title": "Authoritative source title",
      "url": "https://example.com/source",
      "publisher": "Publisher",
      "published_at": "2026-08-01",
      "accessed_at": "2026-09-01"
    }
  ],
  "claims": [
    {
      "claim_id": "CLM-001",
      "status": "confirmed",
      "current_finding": "What the current source establishes.",
      "evidence": ["WEB-001"],
      "confidence": "high"
    }
  ]
}
```

Allowed statuses are `confirmed`, `updated`, `conflicted`, and `unverified`.

## `knowledge.json`

```json
{
  "purpose": "What this generated skill helps an agent do.",
  "topics": [
    {
      "title": "Topic title",
      "summary": "Source-grounded guidance.",
      "evidence": ["VID-001", "WEB-001"]
    }
  ],
  "procedures": [
    {
      "title": "Procedure title",
      "summary": "When to use the procedure.",
      "evidence": ["VID-002"],
      "steps": [
        {
          "text": "A validated action.",
          "evidence": ["VID-002", "FRM-001"]
        }
      ]
    }
  ],
  "examples": [
    {
      "title": "Example title",
      "content": "A concise example synthesized from the evidence.",
      "evidence": ["VID-003"]
    }
  ],
  "unresolved_questions": []
}
```

Knowledge evidence must reference identifiers present in the analysis or declared research sources. Do not put unsupported prose into these files.
