import os
import threading
from datetime import datetime
from llama_cpp import Llama
from huggingface_hub import hf_hub_download
import glob

# Configuration
def find_local_model():
    specific_path = os.path.join(os.getcwd(), "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf")
    if os.path.exists(specific_path):
        return specific_path
    
    gguf_files = glob.glob("*.gguf")
    if gguf_files:
        return os.path.abspath(gguf_files[0])
    
    return os.path.join(os.getcwd(), "models", "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf")

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
            if not os.path.exists(MODEL_PATH):
                os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
                hf_hub_download(
                    repo_id="TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF",
                    filename="tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
                    local_dir=os.path.dirname(MODEL_PATH) if os.path.dirname(MODEL_PATH) else ".",
                    local_dir_use_symlinks=False
                )
            import multiprocessing
            self.model = Llama(
                model_path=MODEL_PATH,
                n_ctx=1024,
                n_threads=min(16, multiprocessing.cpu_count() or 4), # Allow higher max threads for parallelism
                n_batch=16, # Tuned batch matching the user instructions for prompt processing speed
                n_gpu_layers=-1, # Will offload exactly to GPU if you have one + CUDA enabled
                use_mlock=False,
                verbose=False
            )
            print("Nano-Model Ready.")

    def get_context(self):
        # ⚡ Ultra-Compress context for speed
        return "StarZopp: Creative Networking (Film/Music/Fashion). Job Boards, Portfolios, AI Search, Messaging."

    def generate(self, prompt: str, max_tokens: int = 60, temperature: float = 0.2, top_p: float = 0.85):
        clean = prompt.lower().strip().replace(".", "")
        if clean in {"hi", "hello", "hey", "hii"}:
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
        if clean in {"hi", "hello", "hey", "hii"}:
            yield "Hello! I am stazzy, your StarZopp AI. How can I assist you today?"
            return

        if self.model is None:
            self.load_model()

        context = self.get_context()
        formatted_prompt = f"<|im_start|>system\nStarZopp Expert. Database: {context}<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"

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
            
            for output in stream:
                token = output["choices"][0]["text"]
                if token:
                    yield token



llm = LLMManager()
