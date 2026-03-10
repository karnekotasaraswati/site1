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

    def generate_stream(self, prompt: str, max_tokens: int = 256, temperature: float = 0.2, top_p: float = 0.9):
        clean_prompt = prompt.lower().strip().replace(".", "").replace("!", "").replace("?", "")
        
        # 🎯 VERIFIED ACCURACY HUB: 0-1s Instant Delivery for Official Facts
        # These are pre-verified answers that bypass the LLM for 100% accuracy.
        instant_facts = {
            "starzopp": "StarZopp is the premier professional networking platform for creative industries (Film, Music, Fashion). We bridge the gap between creative talent and industry opportunities.",
            "what is": "StarZopp is the official networking ecosystem for creatives in Film, Music, and Fashion. It provides dynamic portfolios, messaging, and AI-powered tools for professional growth.",
            "feature": "StarZopp features: 1. Dynamic Portfolios, 2. Real-Time Messaging, 3. AI Smart Search, 4. Job Boards, 5. Growth Analytics, and 6. Verified Professional Profiles.",
            "mission": "Our mission is to provide a centralized digital ecosystem for creative jobs, collaborations, and professional growth globally.",
            "level up": "Leveling up on StarZopp requires Mastering: Strategic Portfolio Curation, Community Engagement, Profile Verification, and Analytics-Driven Optimization.",
            "contact": "You can connect with the StarZopp community directly through the platform's real-time messaging and job boards.",
            "hello": "Hello! I'm stazzy, your Starzopp assistant. I provide verified information about our creative networking platform. How can I help you today?",
            "hi": "Hi there! I'm here to help you navigate StarZopp. What would you like to know about our features or mission?"
        }

        # Priority keyword check for 100% Accuracy + 0s Speed
        for key in instant_facts:
            if key in clean_prompt:
                yield f"[VERIFIED] {instant_facts[key]}"
                return

        if self.model is None:
            self.load_model()

        context = self.get_context()
        # Grounding Prompt: Strictly forces the AI to use ONLY the provided facts.
        formatted_prompt = f"""<|system|>You are the StarZopp Fact Bot. 
RULES:
1. ONLY use the DATABASE below.
2. If the answer is NOT in the DATABASE, say 'I only provide verified StarZopp information.'
3. Be professional and concise.

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
