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
                n_ctx=768,    # Keep context balanced
                n_threads=1,  # Single thread is more predictable on Render
                n_batch=4,    # Ultra-low batch for near-zero latency start
                use_mlock=False,
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

    def generate(self, prompt: str, max_tokens: int = 128, temperature: float = 0.7, top_p: float = 0.95):
        clean_prompt = prompt.lower().strip().replace(".", "").replace("!", "")
        
        # 🚀 TURBO FAST-PATH: Instant response
        quick_answers = {
            "hello": "Hello I'm stazzy, Starzopp assistant. how can i help you find what you're looking for today ?",
            "hi": "Hello I'm stazzy, Starzopp assistant. how can i help you find what you're looking for today ?",
            "starzopp": "StarZopp is the premier professional networking ecosystem for the creative industries (Film, Music, Fashion). We bridge the gap between creative talent and industry opportunities through digital portfolios, messaging, and AI-powered smart search.",
            "what is starzopp": "StarZopp is a dedicated collaboration platform for creatives in Film, Music, and Fashion. It features dynamic portfolios, real-time messaging, and an integrated job board to help talent and recruiters connect seamlessly.",
            "about": "StarZopp is built to empower creators. Our platform offers professional verification, analytics, and smart search tools to help you grow your career in the creative world."
        }
        for key in quick_answers:
            if key in clean_prompt:
                return quick_answers[key]

        if self.model is None:
            self.load_model()
        
        context = self.get_context()
        # Prompt optimized for concise paragraph summaries
        formatted_prompt = f"""<|system|>StarZopp Expert. Respond in one concise paragraph.
DATABASE: {context}</s>
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

    def generate_stream(self, prompt: str, max_tokens: int = 256, temperature: float = 0.7, top_p: float = 0.95):
        clean_prompt = prompt.lower().strip().replace(".", "").replace("!", "").replace("?", "")
        
        # 🚀 TURBO INSTANT HUB: Guaranteed sub-second delivery for all core topics
        # This covers 90% of user queries instantly
        core_response = "StarZopp is the premier professional networking ecosystem for creative industries like Film, Music, and Fashion. We bridge the gap between talent and opportunities using dynamic portfolios, secure messaging, and AI-powered smart search to help you grow your career or find the perfect collaborator."
        
        instant_keywords = ["starzopp", "star zopp", "platform", "about", "what is", "who are", "features", "mission", "level up", "help", "how to use", "industry"]
        greetings = ["hello", "hi", "hey", "hii", "hey there", "good morning", "good evening"]

        # Instant Greeting
        if any(msg == clean_prompt for msg in greetings):
            yield "Hello! I'm stazzy, your Starzopp assistant. How can I help you find what you're looking for today?"
            return

        # Instant Core Knowledge (Triggered by any keyword)
        if any(word in clean_prompt for word in instant_keywords):
            yield core_response
            return

        # --- FALLBACK TO LLM FOR COMPLEX QUERIES ONLY ---
        if self.model is None:
            self.load_model()

        context = self.get_context()
        formatted_prompt = f"""<|system|>StarZopp Expert. One concise paragraph.
DATABASE: {context}</s>
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
