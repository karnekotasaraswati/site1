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
        """Initializes the Llama model into memory. Guaranteed to run only once."""
        with self._lock:
            if self.model is not None:
                print("DIAGNOSTIC: Model already loaded. Skipping initialization.")
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
            cpu_count = multiprocessing.cpu_count()
            threads = max(4, cpu_count) if cpu_count else 4
            
            print(f"Initializing Llama with {threads} threads. This happens ONLY ONCE.")
            self.model = Llama(
                model_path=MODEL_PATH,
                n_ctx=2048,
                n_threads=threads, 
                n_batch=512,
                n_gpu_layers=0,
                use_mlock=False,
                verbose=False
            )
            print(f"✅ Qwen-0.5B Model Ready and Loaded into memory.")

    def get_context(self):
        return "StarZopp: Creative Networking (Film/Music/Fashion). Job Boards, Portfolios, AI Search, Messaging."

    def generate(self, prompt: str, max_tokens: int = 60, temperature: float = 0.2, top_p: float = 0.85, system_prompt: str = None):
        clean = prompt.lower().strip().replace(".", "")
        if clean in {"hi", "hello", "hey", "hii", "hloo", "heloo", "helo", "hlo"}:
            return "Hello! I am stazzy, your StarZopp Assistant. How can I help you today?"

        if self.model is None:
            print("CRITICAL ERROR: AI model was not pre-warmed. Initializing now (expect delay)...")
            self.load_model()
        
        sys_str = system_prompt if system_prompt else f"StarZopp Expert. Database: {self.get_context()}"
        formatted_prompt = f"<|im_start|>system\n{sys_str}<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
        
        with self._lock:
            response = self.model(
                formatted_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stop=["<|im_end|>", "\n\nUser:"],
                echo=False
            )
        
        return response["choices"][0]["text"].strip()

    def generate_stream(self, prompt: str, max_tokens: int = 60, temperature: float = 0.2, top_p: float = 0.85):
        clean = prompt.lower().strip().replace(".", "")
        if clean in {"hi", "hello", "hey", "hii", "hloo", "heloo", "helo", "hlo"}:
            yield "Hello! I am stazzy, your StarZopp AI. How can I assist you today?"
            return

        if self.model is None:
            print("CRITICAL ERROR: AI model was not pre-warmed for streaming. Initializing now...")
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
            tokens = []
            for output in stream:
                token = output["choices"][0]["text"]
                if token:
                    tokens.append(token)

        for token in tokens:
            yield token



llm = LLMManager()
