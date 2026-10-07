"""Train YOLOv8n on aircraft defect dataset (Innovation Hangar v2).
Saves to runs/detect/train/weights/best.pt
"""
import os
import sys
from pathlib import Path
from ultralytics import YOLO
import torch

def main():
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"Using GPU: {torch.cuda.get_device_name(0)}")
        device = 0
    else:
        print("Using CPU")
        device = "cpu"

    backend = Path(__file__).resolve().parents[1]
    data_yaml = backend / "data" / "vision_dataset" / "data.yaml"
    project_dir = backend / "runs" / "detect"
    
    if not data_yaml.exists():
        print(f"Dataset config not found at: {data_yaml}")
        return 1

    model = YOLO("yolov8n.pt")
    
    # Train for 15 epochs with reasonable batch size
    results = model.train(
        data=str(data_yaml),
        epochs=15,
        imgsz=640,
        batch=16,
        device=device,
        project=str(project_dir),
        name="train",
        exist_ok=True,
        workers=2,
        pretrained=True,
        verbose=True,
    )
    
    best_weights = project_dir / "train" / "weights" / "best.pt"
    if best_weights.exists():
        print(f"SUCCESS: Trained weights saved to {best_weights}")
    else:
        print("Training finished but best.pt not found where expected.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
