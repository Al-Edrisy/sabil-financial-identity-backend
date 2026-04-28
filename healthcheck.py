import http.client
import sys

def check_health():
    try:
        conn = http.client.HTTPConnection("localhost", 8000)
        conn.request("GET", "/api/v1/health")
        response = conn.getresponse()
        if response.status == 200:
            print("Health check passed")
            sys.exit(0)
        else:
            print(f"Health check failed with status: {response.status}")
            sys.exit(1)
    except Exception as e:
        print(f"Health check failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    check_health()
