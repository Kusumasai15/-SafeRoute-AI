"""Rebuild the reproducible synthetic dataset and train its demo estimator."""
import json

from app.services.lighting_ml import (
    DATASET_SEED,
    DATASET_PATH,
    train_and_evaluate,
    write_demo_dataset,
)


def main():
    records = write_demo_dataset(seed=DATASET_SEED)
    _, metrics, metadata = train_and_evaluate(records)
    print(json.dumps({
        "dataset": str(DATASET_PATH),
        "dataset_records": len(records),
        "evaluation_label": metadata["evaluation_label"],
        "metrics": metrics,
        "model_status": metadata["status"],
    }, indent=2))


if __name__ == "__main__":
    main()
