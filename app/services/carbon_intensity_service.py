import os
import httpx
from sqlalchemy.orm import Session
from ..models import RegionCarbonIntensity


AWS_REGION_TO_ZONE = {
    "us-east-1": "US-MIDA-PJM",
    "us-west-1": "US-NW",
    "eu-west-1": "IE",
    "eu-central-1": "DE",
    "ap-south-1": "IN-SO",
    "ap-southeast-1": "SG",
}


def get_carbon_intensity(db: Session, region: str):
    api_key = os.getenv("ELECTRICITY_MAPS_API_KEY")
    zone = AWS_REGION_TO_ZONE.get(region)

    if api_key and zone:
        try:
            response = httpx.get(
                "https://api.electricitymaps.com/v3/carbon-intensity/latest",
                params={"zone": zone},
                headers={"auth-token": api_key},
                timeout=10
            )

            # print("Electricity Maps status:", response.status_code)
            # print("Electricity Maps response:", response.text)

            if response.status_code == 200:
                data = response.json()
                return float(data["carbonIntensity"])
        except Exception:
            pass

    # Database fallback
    region_data = db.query(
        RegionCarbonIntensity
    ).filter(
        RegionCarbonIntensity.region == region
    ).first()

    if not region_data:
        raise Exception("Region not found")

    return region_data.carbon_intensity_g_per_kwh