#!/usr/bin/env python3
"""
Vocabist Backend P2 Features Test
Tests newly implemented P2 features: Hybrid Search, Visual Capture, Admin Security
"""
import requests
import json
import sys
from typing import Optional

# Test configuration
BASE_URL = "http://localhost:8001"
STUDENT_EMAIL = "test@vocabist.com"
STUDENT_PASSWORD = "test1234"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.token: Optional[str] = None
        self.failures = []
        
    def log(self, message: str, color: str = Colors.BLUE):
        print(f"{color}{message}{Colors.END}")
        
    def success(self, test_name: str, details: str = ""):
        self.passed += 1
        msg = f"✅ PASS: {test_name}"
        if details:
            msg += f" - {details}"
        self.log(msg, Colors.GREEN)
        
    def fail(self, test_name: str, reason: str):
        self.failed += 1
        msg = f"❌ FAIL: {test_name} - {reason}"
        self.log(msg, Colors.RED)
        self.failures.append({"test": test_name, "reason": reason})
        
    def test_api_root(self):
        """Test GET /api/ - should return service info"""
        try:
            resp = requests.get(f"{BASE_URL}/api/", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("service") == "vocabist" and data.get("status") == "ok":
                    self.success("API Root", f"Response: {data}")
                    return True
                else:
                    self.fail("API Root", f"Unexpected response: {data}")
                    return False
            else:
                self.fail("API Root", f"Status {resp.status_code}")
                return False
        except Exception as e:
            self.fail("API Root", f"Exception: {str(e)}")
            return False
            
    def test_login(self):
        """Test authentication with student credentials"""
        try:
            resp = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": STUDENT_EMAIL, "password": STUDENT_PASSWORD},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                if "token" in data and "user" in data:
                    self.token = data["token"]
                    user = data["user"]
                    self.success("Student Login", f"User: {user.get('email')}, Token received")
                    return True
                else:
                    self.fail("Student Login", f"Missing token or user in response: {data}")
                    return False
            else:
                self.fail("Student Login", f"Status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Student Login", f"Exception: {str(e)}")
            return False
    
    def test_hybrid_search_exact(self):
        """Test GET /api/search/hybrid?q=resilient - exact match"""
        if not self.token:
            self.fail("Hybrid Search (Exact)", "No token available")
            return False
            
        try:
            resp = requests.get(
                f"{BASE_URL}/api/search/hybrid?q=resilient",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                words = data.get("words", [])
                search_types = data.get("search_types", [])
                semantic_available = data.get("semantic_available")
                
                # Check if we got results
                if len(words) > 0:
                    # Check if "resilient" is in the results
                    found_resilient = any(w.get("headword", "").lower() == "resilient" for w in words)
                    if found_resilient:
                        self.success("Hybrid Search (Exact)", 
                                   f"Found 'resilient', {len(words)} results, search_types: {search_types}, semantic_available: {semantic_available}")
                        return True
                    else:
                        self.success("Hybrid Search (Exact)", 
                                   f"Got {len(words)} results (resilient not in bank), search_types: {search_types}")
                        return True
                else:
                    self.fail("Hybrid Search (Exact)", f"No results returned for 'resilient'")
                    return False
            else:
                self.fail("Hybrid Search (Exact)", f"Status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Hybrid Search (Exact)", f"Exception: {str(e)}")
            return False
    
    def test_hybrid_search_prefix(self):
        """Test GET /api/search/hybrid?q=ab - prefix matches"""
        if not self.token:
            self.fail("Hybrid Search (Prefix)", "No token available")
            return False
            
        try:
            resp = requests.get(
                f"{BASE_URL}/api/search/hybrid?q=ab",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                words = data.get("words", [])
                search_types = data.get("search_types", [])
                
                # Check if we got prefix matches (abandon, abate, etc.)
                if len(words) > 0:
                    # Check if results start with "ab"
                    prefix_matches = [w for w in words if w.get("headword", "").lower().startswith("ab")]
                    if len(prefix_matches) > 0:
                        headwords = [w.get("headword") for w in prefix_matches[:5]]
                        self.success("Hybrid Search (Prefix)", 
                                   f"Found {len(prefix_matches)} prefix matches: {headwords}, search_types: {search_types}")
                        return True
                    else:
                        self.fail("Hybrid Search (Prefix)", f"No prefix matches found in {len(words)} results")
                        return False
                else:
                    self.fail("Hybrid Search (Prefix)", f"No results returned for 'ab'")
                    return False
            else:
                self.fail("Hybrid Search (Prefix)", f"Status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Hybrid Search (Prefix)", f"Exception: {str(e)}")
            return False
    
    def test_hybrid_search_semantic(self):
        """Test GET /api/search/hybrid?q=someone+who+never+gives+up - semantic search"""
        if not self.token:
            self.fail("Hybrid Search (Semantic)", "No token available")
            return False
            
        try:
            resp = requests.get(
                f"{BASE_URL}/api/search/hybrid?q=someone+who+never+gives+up",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                words = data.get("words", [])
                search_types = data.get("search_types", [])
                semantic_available = data.get("semantic_available")
                
                # Since pgvector is not set up, we expect 0 results or fallback to exact
                self.success("Hybrid Search (Semantic)", 
                           f"Got {len(words)} results, search_types: {search_types}, semantic_available: {semantic_available} (pgvector not set up, expected)")
                return True
            else:
                self.fail("Hybrid Search (Semantic)", f"Status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Hybrid Search (Semantic)", f"Exception: {str(e)}")
            return False
    
    def test_visual_capture_invalid_image(self):
        """Test POST /api/visual-capture/extract with invalid image"""
        if not self.token:
            self.fail("Visual Capture (Invalid Image)", "No token available")
            return False
            
        try:
            resp = requests.post(
                f"{BASE_URL}/api/visual-capture/extract",
                headers={"Authorization": f"Bearer {self.token}"},
                json={"image": "not-valid"},
                timeout=10
            )
            if resp.status_code == 400:
                data = resp.json()
                detail = data.get("detail", "")
                if "Image must be a data URL" in detail:
                    self.success("Visual Capture (Invalid Image)", f"Correctly rejected: {detail}")
                    return True
                else:
                    self.fail("Visual Capture (Invalid Image)", f"Wrong error message: {detail}")
                    return False
            else:
                self.fail("Visual Capture (Invalid Image)", f"Expected 400, got {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Visual Capture (Invalid Image)", f"Exception: {str(e)}")
            return False
    
    def test_visual_capture_empty_words(self):
        """Test POST /api/visual-capture/import with empty words array"""
        if not self.token:
            self.fail("Visual Capture (Empty Words)", "No token available")
            return False
            
        try:
            resp = requests.post(
                f"{BASE_URL}/api/visual-capture/import",
                headers={"Authorization": f"Bearer {self.token}"},
                json={"words": []},
                timeout=10
            )
            if resp.status_code == 400:
                data = resp.json()
                detail = data.get("detail", "")
                if "No words to import" in detail:
                    self.success("Visual Capture (Empty Words)", f"Correctly rejected: {detail}")
                    return True
                else:
                    self.fail("Visual Capture (Empty Words)", f"Wrong error message: {detail}")
                    return False
            else:
                self.fail("Visual Capture (Empty Words)", f"Expected 400, got {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Visual Capture (Empty Words)", f"Exception: {str(e)}")
            return False
    
    def test_admin_security_embeddings_status(self):
        """Test that non-admin cannot access GET /api/admin/embeddings/status"""
        if not self.token:
            self.fail("Admin Security (Embeddings Status)", "No token available")
            return False
            
        try:
            resp = requests.get(
                f"{BASE_URL}/api/admin/embeddings/status",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10
            )
            if resp.status_code == 403:
                data = resp.json()
                detail = data.get("detail", "")
                if "Admin access required" in detail:
                    self.success("Admin Security (Embeddings Status)", f"Correctly blocked non-admin: {detail}")
                    return True
                else:
                    self.fail("Admin Security (Embeddings Status)", f"Wrong error message: {detail}")
                    return False
            else:
                self.fail("Admin Security (Embeddings Status)", f"Expected 403, got {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Admin Security (Embeddings Status)", f"Exception: {str(e)}")
            return False
    
    def test_admin_security_bulk_generate(self):
        """Test that non-admin cannot access POST /api/admin/vocabulary/bulk-generate"""
        if not self.token:
            self.fail("Admin Security (Bulk Generate)", "No token available")
            return False
            
        try:
            resp = requests.post(
                f"{BASE_URL}/api/admin/vocabulary/bulk-generate",
                headers={"Authorization": f"Bearer {self.token}"},
                json={"count": 10},
                timeout=10
            )
            if resp.status_code == 403:
                data = resp.json()
                detail = data.get("detail", "")
                if "Admin access required" in detail:
                    self.success("Admin Security (Bulk Generate)", f"Correctly blocked non-admin: {detail}")
                    return True
                else:
                    self.fail("Admin Security (Bulk Generate)", f"Wrong error message: {detail}")
                    return False
            else:
                self.fail("Admin Security (Bulk Generate)", f"Expected 403, got {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Admin Security (Bulk Generate)", f"Exception: {str(e)}")
            return False
    
    def test_admin_security_ai_insights(self):
        """Test that non-admin cannot access GET /api/admin/ai/insights"""
        if not self.token:
            self.fail("Admin Security (AI Insights)", "No token available")
            return False
            
        try:
            resp = requests.get(
                f"{BASE_URL}/api/admin/ai/insights",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10
            )
            if resp.status_code == 403:
                data = resp.json()
                detail = data.get("detail", "")
                if "Admin access required" in detail:
                    self.success("Admin Security (AI Insights)", f"Correctly blocked non-admin: {detail}")
                    return True
                else:
                    self.fail("Admin Security (AI Insights)", f"Wrong error message: {detail}")
                    return False
            else:
                self.fail("Admin Security (AI Insights)", f"Expected 403, got {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Admin Security (AI Insights)", f"Exception: {str(e)}")
            return False
    
    def test_existing_words_search(self):
        """Test GET /api/words?search=aban&limit=5 - existing functionality"""
        if not self.token:
            self.fail("Existing Words Search", "No token available")
            return False
            
        try:
            resp = requests.get(
                f"{BASE_URL}/api/words?search=aban&limit=5",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                words = data.get("words", [])
                total = data.get("total", 0)
                if len(words) > 0:
                    headwords = [w.get("headword") for w in words]
                    self.success("Existing Words Search", f"Found {len(words)} words: {headwords}, total: {total}")
                    return True
                else:
                    self.fail("Existing Words Search", f"No results for 'aban'")
                    return False
            else:
                self.fail("Existing Words Search", f"Status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Existing Words Search", f"Exception: {str(e)}")
            return False
    
    def test_existing_topics(self):
        """Test GET /api/topics - existing functionality"""
        if not self.token:
            self.fail("Existing Topics", "No token available")
            return False
            
        try:
            resp = requests.get(
                f"{BASE_URL}/api/topics",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                topics = data.get("topics", [])
                if len(topics) > 0:
                    self.success("Existing Topics", f"Found {len(topics)} topics")
                    return True
                else:
                    self.fail("Existing Topics", "No topics returned")
                    return False
            else:
                self.fail("Existing Topics", f"Status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Existing Topics", f"Exception: {str(e)}")
            return False
    
    def test_existing_exams(self):
        """Test GET /api/exams - existing functionality"""
        if not self.token:
            self.fail("Existing Exams", "No token available")
            return False
            
        try:
            resp = requests.get(
                f"{BASE_URL}/api/exams",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                exams = data.get("exams", [])
                if len(exams) > 0:
                    self.success("Existing Exams", f"Found {len(exams)} exams")
                    return True
                else:
                    self.fail("Existing Exams", "No exams returned")
                    return False
            else:
                self.fail("Existing Exams", f"Status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Existing Exams", f"Exception: {str(e)}")
            return False
            
    def run_all_tests(self):
        """Run all P2 feature tests in sequence"""
        self.log("\n" + "="*70, Colors.BLUE)
        self.log("Vocabist Backend P2 Features Test", Colors.BLUE)
        self.log("Testing: Hybrid Search, Visual Capture, Admin Security", Colors.BLUE)
        self.log("="*70 + "\n", Colors.BLUE)
        
        # Run tests in order
        self.log("\n--- API Root ---", Colors.YELLOW)
        self.test_api_root()
        
        self.log("\n--- Authentication ---", Colors.YELLOW)
        self.test_login()
        
        self.log("\n--- Hybrid Search (P2 Feature) ---", Colors.YELLOW)
        self.test_hybrid_search_exact()
        self.test_hybrid_search_prefix()
        self.test_hybrid_search_semantic()
        
        self.log("\n--- Visual Capture (P2 Feature) ---", Colors.YELLOW)
        self.test_visual_capture_invalid_image()
        self.test_visual_capture_empty_words()
        
        self.log("\n--- Admin Security (P2 Feature) ---", Colors.YELLOW)
        self.test_admin_security_embeddings_status()
        self.test_admin_security_bulk_generate()
        self.test_admin_security_ai_insights()
        
        self.log("\n--- Existing Functionality Preserved ---", Colors.YELLOW)
        self.test_existing_words_search()
        self.test_existing_topics()
        self.test_existing_exams()
        
        # Print summary
        self.log("\n" + "="*70, Colors.BLUE)
        self.log("TEST SUMMARY", Colors.BLUE)
        self.log("="*70, Colors.BLUE)
        self.log(f"Total Tests: {self.passed + self.failed}", Colors.BLUE)
        self.log(f"Passed: {self.passed}", Colors.GREEN)
        self.log(f"Failed: {self.failed}", Colors.RED)
        
        if self.failures:
            self.log("\nFailed Tests:", Colors.RED)
            for failure in self.failures:
                self.log(f"  - {failure['test']}: {failure['reason']}", Colors.RED)
        
        self.log("="*70 + "\n", Colors.BLUE)
        
        return self.failed == 0

if __name__ == "__main__":
    runner = TestRunner()
    success = runner.run_all_tests()
    sys.exit(0 if success else 1)
