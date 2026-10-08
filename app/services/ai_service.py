import os
import json
import httpx
from typing import Dict, Any, Optional
from pydantic import ValidationError
from ..schemas import AIOptimizationResponse

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
# Primary model with fallbacks
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama3-70b-8192",
    "mixtral-8x7b-32768"
]


def get_ai_system_prompt() -> str:
    return (
        "You are an expert CI/CD Sustainability & Resource Optimization Engineer for GreenCICD.\n"
        "Your task is to analyze GitHub Actions workflow YAML files and empirical pipeline execution telemetry "
        "(CPU usage %, Memory usage %, duration, energy in kWh, carbon in g CO2) to produce actionable, evidence-based recommendations.\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. DO NOT invent measurements or carbon calculations. Rely strictly on the provided telemetry numbers.\n"
        "2. Focus on practical CI/CD optimizations such as:\n"
        "   - Adding missing dependency caching (e.g. actions/setup-node, actions/setup-python, actions/cache)\n"
        "   - Eliminating duplicate or unoptimized workflow triggers\n"
        "   - Parallelizing independent build steps or jobs\n"
        "   - Reducing idle runtime and CPU/memory waste\n"
        "   - Optimizing checkout fetch depth (e.g. fetch-depth: 1)\n"
        "3. Provide exactly 2 to 3 high-impact, specific recommendations based on the actual workflow YAML and telemetry.\n"
        "4. Your response MUST be valid JSON matching this exact structure:\n"
        "{\n"
        '  "summary": "Short executive summary of the workflow efficiency analysis",\n'
        '  "recommendations": [\n'
        "    {\n"
        '      "title": "Short title",\n'
        '      "priority": "high" | "medium" | "low",\n'
        '      "problem": "Specific bottleneck identified",\n'
        '      "evidence": "Concrete proof from YAML lines or telemetry numbers",\n'
        '      "recommendation": "Step-by-step resolution guidance",\n'
        '      "expected_impact": "Estimated percentage or qualitative reduction in energy/carbon",\n'
        '      "effort": "low" | "medium" | "high"\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )


async def enhance_recommendations_with_groq(
    deterministic_data: Dict[str, Any],
    project_name: str,
    repo_url: str,
    workflow_yaml: Optional[str],
    telemetry_summary: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Attempts to enhance deterministic recommendations using Groq LLM API.
    If GROQ_API_KEY is missing, rate-limited, or unavailable, seamlessly returns
    the deterministic rule engine's recommendations so the user ALWAYS receives output.
    """
    groq_api_key = os.getenv("GROQ_API_KEY")

    if not groq_api_key or groq_api_key.strip() == "":
        # Graceful fallback: return deterministic recommendations directly
        return deterministic_data

    # Format user prompt with sanitized, relevant context
    user_prompt = f"""Project: {project_name} ({repo_url})

TELEMETRY DATA:
- Recorded Runs: {telemetry_summary.get("total_runs", 0)}
- Average Duration: {telemetry_summary.get("avg_duration_minutes", 0)} minutes
- Average CPU Usage: {telemetry_summary.get("avg_cpu_usage", 0)}%
- Average Memory Usage: {telemetry_summary.get("avg_memory_usage", 0)}%
- Total Energy Consumed: {telemetry_summary.get("total_energy_kwh", 0)} kWh
- Total Carbon Emissions: {telemetry_summary.get("total_carbon_grams", 0)} g CO2
- Runner Region: {telemetry_summary.get("latest_region", "us-east-1")}

WORKFLOW YAML (.github/workflows/greencicd.yml):
```yaml
{workflow_yaml or "# Workflow file missing or empty"}
```

DETERMINISTIC INITIAL FINDINGS:
{json.dumps(deterministic_data, indent=2)}

Please refine these recommendations into the final JSON output format with 2 to 3 actionable recommendations.
"""

    headers = {
        "Authorization": f"Bearer {groq_api_key.strip()}",
        "Content-Type": "application/json"
    }

    # Try model hierarchy starting with llama-3.3-70b-versatile
    for model_name in GROQ_MODELS:
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": get_ai_system_prompt()},
                {"role": "user", "content": user_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(GROQ_API_URL, headers=headers, json=payload)

                if res.status_code == 200:
                    data = res.json()
                    raw_content = data["choices"][0]["message"]["content"]
                    
                    # Validate JSON response against Pydantic schema
                    validated = AIOptimizationResponse.model_validate_json(raw_content)
                    return validated.model_dump()
                
                print(f"Groq API model '{model_name}' returned status {res.status_code}: {res.text}")

        except ValidationError as ve:
            print(f"Pydantic validation error for Groq response using model '{model_name}':", ve)
        except Exception as e:
            print(f"Groq API connection error using model '{model_name}':", e)

    # Seamless fallback: return deterministic recommendations if Groq is unavailable
    return deterministic_data
