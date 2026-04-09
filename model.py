import os
import threading
from datetime import datetime
from llama_cpp import Llama
from huggingface_hub import hf_hub_download
import glob

# Configuration
def find_local_model():
    specific_path = os.path.join(os.getcwd(), "qwen1_5-0_5b-chat-q4_k_m.gguf")
    if os.path.exists(specific_path):
        return specific_path
    
    gguf_files = glob.glob("*.gguf")
    if gguf_files:
        return os.path.abspath(gguf_files[0])
    
    return os.path.join(os.getcwd(), "models", "qwen1_5-0_5b-chat-q4_k_m.gguf")

MODEL_PATH = find_local_model()

class LLMManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LLMManager, cls).__new__(cls)
            cls._instance.model = None
        return cls._instance

    def load_model(self):
        with self._lock:
            if self.model is not None:
                return

            print(f"Loading Nano-model: {MODEL_PATH}")
            if os.path.exists(MODEL_PATH) and os.path.getsize(MODEL_PATH) < 100_000_000:
                print("Detected corrupted or incomplete model file. Removing and re-downloading...")
                os.remove(MODEL_PATH)

            if not os.path.exists(MODEL_PATH):
                os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
                print(f"Downloading Qwen model from HuggingFace... Path: {MODEL_PATH}")
                hf_hub_download(
                    repo_id="Qwen/Qwen1.5-0.5B-Chat-GGUF",
                    filename="qwen1_5-0_5b-chat-q4_k_m.gguf",
                    local_dir=os.path.dirname(MODEL_PATH) if os.path.dirname(MODEL_PATH) else ".",
                    local_dir_use_symlinks=False
                )
            import multiprocessing
            # Cap threads to 2 for Render Free Tier to prevent massive context-switching overhead
            cores = multiprocessing.cpu_count() if multiprocessing.cpu_count() else 1
            self.model = Llama(
                model_path=MODEL_PATH,
                n_ctx=1024,
                n_threads=min(2, cores), 
                n_batch=16, 
                n_gpu_layers=-1, 
                use_mlock=False,
                verbose=False
            )
            print(f"Qwen-0.5B Model Ready. Loaded from {MODEL_PATH}")

    def get_context(self):
        # ⚡ Ultra-Compress context for speed
        return "StarZopp: Creative Networking (Film/Music/Fashion). Job Boards, Portfolios, AI Search, Messaging."

    def generate(self, prompt: str, max_tokens: int = 60, temperature: float = 0.2, top_p: float = 0.85):
        clean = prompt.lower().strip().replace(".", "")
        if clean in {"hi", "hello", "hey", "hii", "hloo", "heloo", "helo", "hlo"}:
            return "Hello! I am stazzy, your StarZopp Assistant. How can I help you today?"

        if self.model is None:
            self.load_model()
        
        context = self.get_context()
        formatted_prompt = f"<|im_start|>system\nStarZopp Expert. Database: {context}<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
        
        with self._lock:
            response = self.model(
                formatted_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stop=["<|im_end|>", "\n\nUser:"], # Aggressive heuristics stopping
                echo=False
            )
        
        return response["choices"][0]["text"].strip()

    def generate_stream(self, prompt: str, max_tokens: int = 60, temperature: float = 0.2, top_p: float = 0.85):
        # 🚀 IMMEDIATE GREETING HANDOFF (0.01s)
        clean = prompt.lower().strip().replace(".", "")
        if clean in {"hi", "hello", "hey", "hii", "hloo", "heloo", "helo", "hlo"}:
            yield "Hello! I am stazzy, your StarZopp AI. How can I assist you today?"
            return

        if self.model is None:
            self.load_model()

        context = self.get_context()
        formatted_prompt = f"<|im_start|>system\nStarZopp Expert. Database: {context}<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"

        # Acquire lock only to START the stream, not hold it for the full generation
        with self._lock:
            stream = self.model(
                formatted_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stop=["<|im_end|>", "\n\nUser:"],
                stream=True,
                echo=False
            )
            # Collect all tokens while holding the lock (llama_cpp stream is not thread-safe)
            tokens = []
            for output in stream:
                token = output["choices"][0]["text"]
                if token:
                    tokens.append(token)

        # Yield tokens AFTER releasing the lock so other threads can proceed
        for token in tokens:
            yield token



llm = LLMManager()
