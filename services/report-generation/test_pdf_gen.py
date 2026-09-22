import os
import json
from report_engine.generators.pdf_generator import generate_pdf_report
from report_engine.generators.data_provider import enhance_report_data

def run_test():
    # Load sample JSON data from somewhere, or generate a dummy one
    # If the user has a real test.json, we can load it. Let's see if there's one.
    sample_json_path = os.path.join(os.path.dirname(__file__), "data", "test_report_data.json")
    if os.path.exists(sample_json_path):
        with open(sample_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        print("No sample data found, generating dummy.")
        # Minimal mock data to satisfy enhance_report_data
        data = {
            "year": 2024,
            "month": "all",
            "kpis": {
                "gross": {"value": 1500, "trend": {"raw": -5, "good": True}},
                "net": {"value": 1400, "trend": {"raw": -5, "good": True}},
                "avoid": {"value": 100, "trend": {"raw": 10, "good": True}},
                "scope1": {"value": 500, "trend": {"raw": 2, "good": False}},
                "scope2": {"value": 1000, "trend": {"raw": -10, "good": True}},
                "elec": {"value": 2000000, "trend": {"raw": -2, "good": True}},
                "re": {"value": 500000, "trend": {"raw": 10, "good": True}},
                "reShare": {"value": 20, "trend": {"raw": 5, "good": True}},
                "petrolL": {"value": 5000, "trend": {"raw": 1, "good": False}},
                "petrolEm": {"value": 12, "trend": {"raw": 1, "good": False}},
                "trDieselL": {"value": 20000, "trend": {"raw": 2, "good": False}},
                "trDieselEm": {"value": 54, "trend": {"raw": 2, "good": False}},
                "dgEm": {"value": 15, "trend": {"raw": -5, "good": True}},
                "perCapita": {"value": 0.25, "trend": {"raw": -1, "good": True}}
            },
            "current_period": {
                "elecKwh": [100000]*12,
                "reKwh": [20000]*12,
                "htKwh": [50000]*12,
                "htEm": [36]*12,
                "commKwh": [10000]*12,
                "commEm": [7.2]*12,
                "tempKwh": [5000]*12,
                "tempEm": [3.6]*12,
                "petrolL": [400]*12,
                "petrolEm": [1]*12,
                "trDieselL": [1500]*12,
                "trDieselEm": [4]*12,
                "dgL": [500]*12,
                "dgEm": [1.3]*12,
                "scope1Selected": [1900]*12
            }
        }
    
    # Enhance data
    data = enhance_report_data(data)
    
    # Generate PDF
    pdf_path = generate_pdf_report(data, {})
    print(f"Generated test PDF at: {pdf_path}")

if __name__ == "__main__":
    run_test()
