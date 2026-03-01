from dotenv import load_dotenv
import json
from agents.video_agent import generate_video_json

load_dotenv()

if __name__ == "__main__":
    script = generate_video_json(topic="减脂早餐", style="种草")
    print(json.dumps(script.model_dump(), indent=2, ensure_ascii=False))