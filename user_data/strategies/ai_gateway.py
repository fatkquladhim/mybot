import os
import json
import time
import requests
import logging

logger = logging.getLogger(__name__)

class SumopodAIGateway:
    """
    Gateway to interact with Sumopod AI Engine (OpenAI-compatible)
    Handles caching, failover (Technical Only mode), and rate limiting.
    """
    
    def __init__(self):
        self.api_key = os.environ.get("SUMOPOD_API_KEY", "")
        self.base_url = os.environ.get("SUMOPOD_BASE_URL", "https://ai.sumopod.com/v1")
        self.model = os.environ.get("SUMOPOD_MODEL", "gemini/gemini-2.5-flash-lite")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # In-memory cache: pair -> { "timestamp": float, "score": int, "narrative": int, "fundamental": int, "reasoning": str }
        self.score_cache = {}
        self.cache_ttl = 3600  # 60 minutes
        
        # Emergency Mode Tracking
        self.consecutive_failures = 0
        self.last_failure_time = 0
        self.emergency_mode = False
        self.emergency_threshold_mins = 10
        
    def _check_emergency_mode(self):
        if self.consecutive_failures > 0:
            down_time = (time.time() - self.last_failure_time) / 60
            if down_time > self.emergency_threshold_mins:
                if not self.emergency_mode:
                    logger.warning("🚨 [AI GATEWAY] SUMOPOD AI DOWN > 10 MINS. SWITCHING TO EMERGENCY TECHNICAL-ONLY MODE!")
                    self.emergency_mode = True
        else:
            if self.emergency_mode:
                logger.info("✅ [AI GATEWAY] SUMOPOD AI RECOVERED. LEAVING EMERGENCY MODE.")
                self.emergency_mode = False
                
    def is_emergency_mode(self):
        self._check_emergency_mode()
        return self.emergency_mode

    def _call_llm(self, pair, context_data):
        """
        Directly call Sumopod AI.
        Returns (success, result_dict)
        """
        prompt = f"""
        Analyze the following trading pair for a spot swing trade.
        Pair: {pair}
        Context Data (Technical/Market): {context_data}
        
        Provide a JSON response with the following keys strictly:
        - "narrative_score": integer (0 to 30)
        - "fundamental_score": integer (0 to 25)
        - "reasoning": string (short 1-2 sentences explaining why)
        
        Do not include markdown blocks, just raw JSON.
        """
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an expert crypto analyst evaluating narrative and fundamental strength."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2
        }
        
        try:
            resp = requests.post(f"{self.base_url}/chat/completions", json=payload, headers=self.headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            content = data['choices'][0]['message']['content']
            
            # Clean possible markdown JSON wrappers
            content = content.replace('```json', '').replace('```', '').strip()
            
            result = json.loads(content)
            
            # Success
            self.consecutive_failures = 0
            
            return True, {
                "narrative": result.get("narrative_score", 0),
                "fundamental": result.get("fundamental_score", 0),
                "reasoning": result.get("reasoning", "No reasoning provided")
            }
            
        except Exception as e:
            logger.error(f"[AI GATEWAY] Error calling Sumopod API for {pair}: {e}")
            if self.consecutive_failures == 0:
                self.last_failure_time = time.time()
            self.consecutive_failures += 1
            self._check_emergency_mode()
            return False, {}

    def get_ai_score(self, pair, context_data, force_refresh=False):
        """
        Get AI Score (Narrative + Fundamental).
        Returns { "narrative": int, "fundamental": int, "reasoning": str, "source": "cache" | "api" | "emergency" }
        """
        # Check Emergency Mode
        if self.is_emergency_mode():
            return {
                "narrative": 0,
                "fundamental": 0,
                "reasoning": "EMERGENCY MODE: AI Unavailable. Technical-Only.",
                "source": "emergency"
            }
            
        # Check Cache
        now = time.time()
        if not force_refresh and pair in self.score_cache:
            cached_data = self.score_cache[pair]
            if now - cached_data['timestamp'] < self.cache_ttl:
                return {
                    "narrative": cached_data['narrative'],
                    "fundamental": cached_data['fundamental'],
                    "reasoning": cached_data['reasoning'],
                    "source": "cache"
                }
                
        # Cache Miss or Force Refresh -> Call API
        logger.info(f"[AI GATEWAY] Fetching new AI score for {pair}...")
        success, ai_data = self._call_llm(pair, context_data)
        
        if success:
            # Update cache
            self.score_cache[pair] = {
                "timestamp": now,
                "narrative": ai_data["narrative"],
                "fundamental": ai_data["fundamental"],
                "reasoning": ai_data["reasoning"]
            }
            ai_data["source"] = "api"
            return ai_data
        else:
            # If fail, but not in emergency mode yet, return 0s temporarily
            return {
                "narrative": 0,
                "fundamental": 0,
                "reasoning": "API Call Failed. Temporary fallback.",
                "source": "error"
            }

    def batch_pre_score(self, pairs_data):
        """
        Pre-score multiple pairs (called in bot_loop_start)
        pairs_data: dict { "BTC/IDR": "Context...", ... }
        """
        logger.info(f"[AI GATEWAY] Starting batch pre-scoring for {len(pairs_data)} pairs...")
        for pair, context in pairs_data.items():
            # Will use cache if valid
            self.get_ai_score(pair, context, force_refresh=False)
            time.sleep(1) # Prevent rate limiting on our end
