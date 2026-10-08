from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from .carbon_service import suggest_optimized_region

def generate_deterministic_recommendations(
    db: Session,
    project_id: Any,
    project_name: str,
    repo_url: str,
    workflow_yaml: Optional[str],
    telemetry_summary: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generates deterministic, evidence-based CI/CD optimization recommendations
    by analyzing actual workflow YAML structure and telemetry metrics.
    Requires ZERO external AI dependencies or API keys.
    """
    recommendations: List[Dict[str, Any]] = []

    # Rule 1: Empirical Region Optimization via Database Carbon Intensity
    try:
        region_opt = suggest_optimized_region(db, project_id)
        if region_opt.get("carbon_reduction_percent", 0) > 0:
            recommendations.append({
                "title": f"Switch CI Runner Region from {region_opt['current_region']} to {region_opt['suggested_region']}",
                "priority": "high",
                "problem": f"Current runner region ({region_opt['current_region']}) has higher carbon grid intensity than available alternatives.",
                "evidence": f"Database grid intensity comparison indicates {region_opt['current_region']} grid carbon intensity is significantly higher than {region_opt['suggested_region']}.",
                "recommendation": f"Update runner region or cloud host location to {region_opt['suggested_region']}. {region_opt['recommendation']}",
                "expected_impact": f"{region_opt['carbon_reduction_percent']}% carbon reduction per build",
                "effort": "low"
            })
    except Exception as e:
        print(f"Region optimization check skipped for project {project_id}:", e)

    # Rule 2: Dependency Caching Inspection in Workflow YAML
    if workflow_yaml:
        yaml_lower = workflow_yaml.lower()
        has_setup_node = "actions/setup-node" in yaml_lower
        has_setup_python = "actions/setup-python" in yaml_lower
        has_cache_step = "actions/cache" in yaml_lower or "cache:" in yaml_lower

        if (has_setup_node or has_setup_python) and not has_cache_step:
            tech = "Node.js (npm/yarn)" if has_setup_node else "Python (pip)"
            cache_flag = "cache: 'npm'" if has_setup_node else "cache: 'pip'"
            recommendations.append({
                "title": f"Enable Dependency Caching for {tech}",
                "priority": "high",
                "problem": "Dependencies are re-downloaded from external registries on every workflow run, wasting network bandwidth and compute time.",
                "evidence": f"Workflow contains `{ 'actions/setup-node' if has_setup_node else 'actions/setup-python' }` without a `cache:` configuration key.",
                "recommendation": f"Add `{cache_flag}` to your setup step in `.github/workflows/greencicd.yml` to cache package dependencies across workflow runs.",
                "expected_impact": "20%–40% reduction in job duration and network transfer",
                "effort": "low"
            })

        # Rule 3: Git Shallow Checkout Inspection
        has_checkout = "actions/checkout" in yaml_lower
        has_fetch_depth = "fetch-depth:" in yaml_lower
        if has_checkout and not has_fetch_depth:
            recommendations.append({
                "title": "Use Shallow Git Checkout (fetch-depth: 1)",
                "priority": "medium",
                "problem": "Full repository commit history is cloned during every build, increasing checkout duration and disk usage.",
                "evidence": "Workflow includes `actions/checkout` without specifying `fetch-depth: 1`.",
                "recommendation": "Add `with: fetch-depth: 1` under `actions/checkout` in `.github/workflows/greencicd.yml` unless git revision history is required for tests.",
                "expected_impact": "Faster checkout step duration and reduced disk footprint",
                "effort": "low"
            })

    # Rule 4: Resource Utilization / Idle Waste Check from Telemetry
    total_runs = telemetry_summary.get("total_runs", 0)
    avg_cpu = telemetry_summary.get("avg_cpu_usage", 0.0)

    if total_runs > 0 and avg_cpu > 0 and avg_cpu < 25.0:
        recommendations.append({
            "title": "Optimize Compute Utilization & Reduce Idle Runtime",
            "priority": "medium",
            "problem": f"Average CPU utilization across recorded runs is low ({avg_cpu:.1f}%), indicating compute resources are idling during workflow execution.",
            "evidence": f"Recorded telemetry across {total_runs} run(s) shows average CPU load of {avg_cpu:.1f}%.",
            "recommendation": "Review CI test steps for unnecessary `sleep` calls or idle waits. Consider running independent test suites in parallel.",
            "expected_impact": "Improved resource efficiency and reduced runner compute duration",
            "effort": "medium"
        })

    # Fallback default if workflow is completely minimalist and no issues flagged
    if not recommendations:
        recommendations.append({
            "title": "Maintain Sustainable CI/CD Best Practices",
            "priority": "low",
            "problem": "No critical configuration inefficiencies detected in current workflow.",
            "evidence": f"Analyzed workflow YAML and telemetry across {total_runs} recorded run(s).",
            "recommendation": "Continue monitoring build durations and consider scheduling non-urgent CI jobs during off-peak hours.",
            "expected_impact": "Maintains low carbon baseline",
            "effort": "low"
        })

    # Summary text
    summary_text = (
        f"GreenCICD Rule Engine analyzed {total_runs} pipeline run(s) and workflow configuration for {project_name}. "
        f"Identified {len(recommendations)} actionable optimization opportunity(ies)."
    )

    return {
        "summary": summary_text,
        "recommendations": recommendations[:3]  # Limit to top 3 recommendations
    }
