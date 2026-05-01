import asyncio
import time
from app.ai.face_match import count_faces

def test():
    with open("tests/fixtures/sample_id.jpg", "rb") as f:
        b = f.read()
    t0 = time.time()
    c = count_faces(b, "test")
    print(f"Faces: {c}, Time: {time.time() - t0:.2f}s")

if __name__ == "__main__":
    test()
