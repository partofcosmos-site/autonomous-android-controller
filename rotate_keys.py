import os
import time
import requests
from typing import List, Optional, Dict, Any

class OpenRouterKeyRotator:
    """
    Manages rotation across multiple OpenRouter API keys to handle
    rate limits (HTTP 429) and quota exhaustion seamlessly.
    """
    def __init__(self, key_prefix: str = "OR_KEY_"):
        self.key_prefix = key_prefix
        self._load_dotenv()
        self.keys: List[str] = self._load_keys()
        self.current_index: int = 0

        if not self.keys:
            # Fallback to standard OPENROUTER_API_KEY if specific numbered keys are not set
            default_key = os.environ.get("OPENROUTER_API_KEY")
            if default_key:
                self.keys.append(default_key)

    def _load_dotenv(self):
        """Loads key-value pairs from .env in the current directory if present."""
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ[k.strip()] = v.strip().strip("\"'")

    def _load_keys(self) -> List[str]:
        keys = []
        # Check standard 1..20 environment variables matching the prefix
        for i in range(1, 21):
            var_name = f"{self.key_prefix}{i}"
            key = os.environ.get(var_name)
            if key and key.strip():
                keys.append(key.strip())
        return keys

    @property
    def current_key(self) -> Optional[str]:
        if not self.keys:
            return None
        return self.keys[self.current_index]

    def rotate_key(self) -> Optional[str]:
        """Advance to the next key in the pool and update process environment."""
        if not self.keys:
            raise ValueError("No API keys found in environment variables.")

        self.current_index = (self.current_index + 1) % len(self.keys)
        new_key = self.keys[self.current_index]
        os.environ["OPENROUTER_API_KEY"] = new_key
        print(f"[KeyRotator] Switched to Key index #{self.current_index + 1} of {len(self.keys)}")
        return new_key

    def send_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        max_retries: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Sends a chat completion request to OpenRouter with automated 429 key failover.
        """
        if not self.keys:
            raise ValueError("No API keys found. Please set OR_KEY_1, OR_KEY_2, etc.")

        retries = max_retries if max_retries is not None else len(self.keys) * 2
        attempts = 0

        while attempts < retries:
            attempts += 1
            api_key = self.current_key
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://autonomous-android-controller.local",
                "X-Title": "Autonomous Android Controller"
            }
            payload: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature
            }
            if max_tokens:
                payload["max_tokens"] = max_tokens

            try:
                response = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60
                )

                if response.status_code == 200:
                    return response.json()

                # Handle Rate Limit / Quota Exhaustion (429) or Payment/Credits Required (402)
                if response.status_code in (429, 402):
                    print(f"[KeyRotator] Received HTTP {response.status_code}. Rotating key...")
                    self.rotate_key()
                    time.sleep(0.5)
                    continue
                else:
                    response.raise_for_status()

            except requests.exceptions.RequestException as e:
                print(f"[KeyRotator] Request error: {e}. Rotating to next key...")
                self.rotate_key()
                time.sleep(0.5)

        raise RuntimeError(f"All {len(self.keys)} API keys exhausted or failed after {attempts} attempts.")


if __name__ == "__main__":
    rotator = OpenRouterKeyRotator()
    print(f"Loaded {len(rotator.keys)} key(s) from environment.")
    if not rotator.keys:
        print("Set OR_KEY_1, OR_KEY_2, etc. in your system to begin.")
