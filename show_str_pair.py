import json
from pathlib import Path

from PIL import Image
import matplotlib.pyplot as plt


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    img_dir = base_dir / "01.원천데이터" / "STR"
    json_dir = base_dir / "02.라벨링데이터" / "STR"

    # Pick the first image in the folder; you can swap to a specific filename.
    img_path = next(img_dir.glob("*.PNG"), None)
    if img_path is None:
        raise FileNotFoundError(f"No PNG files found in {img_dir}")

    json_path = json_dir / f"{img_path.stem}.json"
    if not json_path.exists():
        raise FileNotFoundError(f"Matching JSON not found: {json_path}")

    image = Image.open(img_path)
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Show image
    plt.figure("STR Image")
    plt.imshow(image)
    plt.axis("off")

    # Print JSON to console (readable)
    print(json.dumps(data, ensure_ascii=False, indent=2))

    plt.show()


if __name__ == "__main__":
    main()
