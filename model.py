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

            print(f"Loading model from: {MODEL_PATH}")
            if not os.path.exists(MODEL_PATH):
                os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
                hf_hub_download(
                    repo_id="TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF",
                    filename="tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
                    local_dir=os.path.dirname(MODEL_PATH) if os.path.dirname(MODEL_PATH) else ".",
                    local_dir_use_symlinks=False
                )
            
            self.model = Llama(
                model_path=MODEL_PATH,
                n_ctx=512,  # Reduced from 2048 to save RAM
                n_threads=2, # Reduced from 4 for better stability
                n_batch=128, # Reduced from 512 to save RAM
                verbose=False
            )

            print("Model loaded successfully.")

    def get_context(self):
        knowledge_path = os.path.join(os.getcwd(), "knowledge.txt")
        if os.path.exists(knowledge_path):
            try:
                with open(knowledge_path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except:
                pass
        return ""

    def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7, top_p: float = 0.9):
        # Quick greeting check for 100% accuracy and speed
        clean_prompt = prompt.lower().strip().replace(".", "").replace("!", "")
        if clean_prompt in ["hello", "hi", "hey", "greetings", "hi there"]:
            return "Hello I'm stazzy, Starzopp assistant. how can i help you find what you're looking for today ?"

        if self.model is None:
            self.load_model()
        
        context = self.get_context()
        # Prompt optimized for concise paragraph summaries
        formatted_prompt = f"""<|system|>You are the official StarZopp Expert. 
- The current date and year is {datetime.now().strftime("%B %d, %Y")}.
- Provide a concise, professional summary in a single short paragraph.
- Use ONLY the DATABASE below.
- Do NOT use bullet points unless specifically asked.
- Combine features and mission into a smooth description.

DATABASE:
{context}</s>
<|user|>{prompt}</s>
<|assistant|>"""
        
        with self._lock:
            response = self.model(
                formatted_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stop=["</s>"],
                echo=False
            )
        
        return response["choices"][0]["text"].strip()

    def generate_stream(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7, top_p: float = 0.9):
        # Quick greeting check for 100% accuracy and speed (stream)
        clean_prompt = prompt.lower().strip().replace(".", "").replace("!", "")
        if clean_prompt in ["hello", "hi", "hey", "greetings", "hi there"]:
            yield "Hello I'm stazzy, Starzopp assistant. how can i help you find what you're looking for today ?"
            return

        if self.model is None:
            self.load_model()

        context = self.get_context()
        # Prompt optimized for concise paragraph summaries (stream)
        formatted_prompt = f"""<|system|>You are the official StarZopp Expert. 
- The current date and year is {datetime.now().strftime("%B %d, %Y")}.
- Provide a concise, professional summary in a single short paragraph.
- Use ONLY the DATABASE below.
- Do NOT use bullet points unless specifically asked.
- Combine features and mission into a smooth description.

DATABASE:
{context}</s>
<|user|>{prompt}</s>
<|assistant|>"""

        with self._lock:
            stream = self.model(
                formatted_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stop=["</s>"],
                stream=True,
                echo=False
            )
            
            for output in stream:
                token = output["choices"][0]["text"]
                if token:
                    yield token

llm = LLMManager()
