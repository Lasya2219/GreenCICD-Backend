from sqlalchemy.orm import Session
from ..models import RegionCarbonIntensity
from .carbon_intensity_service import get_carbon_intensity


def calculate_energy(cpu_usage, memory_usage, duration_minutes):
    cpu_power_w = 15 + (cpu_usage / 100) * 35
    memory_power_w = 10 + (memory_usage / 100) * 10

    total_power_w = cpu_power_w + memory_power_w

    pue = 1.2

    energy_kwh = (
        total_power_w
        * pue
        * (duration_minutes / 60)
        / 1000
    )

    return energy_kwh


def calculate_carbon(db: Session, region: str, energy_kwh: float):
    carbon_intensity = get_carbon_intensity(db, region)

    carbon_kg = (
        energy_kwh * carbon_intensity
    ) / 1000

    return carbon_kg

def suggest_optimized_region(db: Session, project_id):

    from ..models import PipelineRun

    # Get latest pipeline run for project
    latest_run = db.query(PipelineRun).filter(
        PipelineRun.project_id == project_id
    ).order_by(PipelineRun.created_at.desc()).first()

    if not latest_run:
        raise Exception("No pipeline runs found for this project")

    current_region = latest_run.region

    current_region_data = db.query(RegionCarbonIntensity).filter(
        RegionCarbonIntensity.region == current_region
    ).first()

    if not current_region_data:
        raise Exception("Current region not found in carbon table")

    best_region = db.query(RegionCarbonIntensity).order_by(
        RegionCarbonIntensity.carbon_intensity_g_per_kwh.asc()
    ).first()

    if not best_region:
        raise Exception("No carbon data available")

    if current_region == best_region.region:
        return {
            "current_region": current_region,
            "suggested_region": best_region.region,
            "carbon_reduction_percent": 0,
            "recommendation": "You are already using the most sustainable region."
        }

    reduction = (
        (current_region_data.carbon_intensity_g_per_kwh -
         best_region.carbon_intensity_g_per_kwh)
        / current_region_data.carbon_intensity_g_per_kwh
    ) * 100

    return {
        "current_region": current_region,
        "suggested_region": best_region.region,
        "carbon_reduction_percent": round(reduction, 2),
        "recommendation": f"Switching from {current_region} to {best_region.region} reduces carbon by {round(reduction,2)}%."
    }