#!/usr/bin/env python3
"""
Vocabist Backend Acceptance Tests
Tests all critical backend endpoints with Supabase + RLS enabled
"""
import requests
import json
import sys
from typing import Optional

# Test configuration
BASE_URL = "http://localhost:8001"
TEST_EMAIL = "demo@vocably.app"
TEST_PASSWORD = "demo1234"

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
        
    def test_health(self):
        """Test basic health endpoint"""
        try:
            resp = requests.get(f"{BASE_URL}/api/", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("service") == "vocabist" and data.get("status") == "ok":
                    self.success("Health Check", "Service is running")
                    return True
                else:
                    self.fail("Health Check", f"Unexpected response: {data}")
                    return False
            else:
                self.fail("Health Check", f"Status {resp.status_code}")
                return False
        except Exception as e:
            self.fail("Health Check", f"Exception: {str(e)}")
            return False
            
    def test_login(self):
        """Test authentication with demo credentials"""
        try:
            resp = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                if "token" in data and "user" in data:
                    self.token = data["token"]
                    user = data["user"]
                    self.success("Login", f"User: {user.get('email')}, Token received")
                    return True
                else:
                    self.fail("Login", f"Missing token or user in response: {data}")
                    return False
            else:
                self.fail("Login", f"Status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Login", f"Exception: {str(e)}")
            return False
            
    def test_auth_me(self):
        """Test /api/auth/me with Bearer token"""
        if not self.token:
            self.fail("Auth Me", "No token available")
            return False
            
        try:
            resp = requests.get(
                f"{BASE_URL}/api/auth/me",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                if "user" in data:
                    user = data["user"]
                    self.success("Auth Me", f"User: {user.get('email')}")
                    return True
                else:
                    self.fail("Auth Me", f"Missing user in response: {data}")
                    return False
            else:
                self.fail("Auth Me", f"Status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Auth Me", f"Exception: {str(e)}")
            return False
            
    def test_words_list(self):
        """Test GET /api/words?limit=5 - should return 231 total words"""
        if not self.token:
            self.fail("Words List", "No token available")
            return False
            
        try:
            resp = requests.get(
                f"{BASE_URL}/api/words?limit=5",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                total = data.get("total", 0)
                words = data.get("words", [])
                if total == 231:
                    self.success("Words List", f"Total: {total}, Returned: {len(words)} words")
                    return True
                else:
                    self.fail("Words List", f"Expected 231 total words, got {total}")
                    return False
            else:
                self.fail("Words List", f"Status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Words List", f"Exception: {str(e)}")
            return False
            
    def test_word_detail(self):
        """Test GET /api/words/abate - word detail with graph"""
        if not self.token:
            self.fail("Word Detail", "No token available")
            return False
            
        try:
            resp = requests.get(
                f"{BASE_URL}/api/words/abate",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                if "word" in data and "graph" in data:
                    word = data["word"]
                    graph = data["graph"]
                    self.success("Word Detail", f"Word: {word.get('headword')}, Graph nodes: {len(graph.get('nodes', []))}")
                    return True
                else:
                    self.fail("Word Detail", f"Missing word or graph in response")
                    return False
            else:
                self.fail("Word Detail", f"Status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Word Detail", f"Exception: {str(e)}")
            return False
            
    def test_topics(self):
        """Test GET /api/topics - should return topics"""
        if not self.token:
            self.fail("Topics", "No token available")
            return False
            
        try:
            resp = requests.get(
                f"{BASE_URL}/api/topics",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                topics = data.get("topics", [])
                if len(topics) > 0:
                    self.success("Topics", f"Found {len(topics)} topics")
                    return True
                else:
                    self.fail("Topics", "No topics returned")
                    return False
            else:
                self.fail("Topics", f"Status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Topics", f"Exception: {str(e)}")
            return False
            
    def test_exams(self):
        """Test GET /api/exams - should return exams"""
        if not self.token:
            self.fail("Exams", "No token available")
            return False
            
        try:
            resp = requests.get(
                f"{BASE_URL}/api/exams",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                exams = data.get("exams", [])
                if len(exams) > 0:
                    self.success("Exams", f"Found {len(exams)} exams")
                    return True
                else:
                    self.fail("Exams", "No exams returned")
                    return False
            else:
                self.fail("Exams", f"Status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Exams", f"Exception: {str(e)}")
            return False
            
    def test_practice_start(self):
        """Test POST /api/practice/start?source=mission - should return questions"""
        if not self.token:
            self.fail("Practice Start", "No token available")
            return False
            
        try:
            resp = requests.post(
                f"{BASE_URL}/api/practice/start?source=mission",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                questions = data.get("questions", [])
                count = data.get("count", 0)
                self.success("Practice Start", f"Returned {count} questions")
                return True
            else:
                self.fail("Practice Start", f"Status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Practice Start", f"Exception: {str(e)}")
            return False
            
    def test_practice_answer(self):
        """Test POST /api/practice/answer - should update XP"""
        if not self.token:
            self.fail("Practice Answer", "No token available")
            return False
            
        # First get a question
        try:
            resp = requests.post(
                f"{BASE_URL}/api/practice/start?source=mission",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10
            )
            if resp.status_code != 200:
                self.fail("Practice Answer", "Could not get practice questions")
                return False
                
            data = resp.json()
            questions = data.get("questions", [])
            if not questions:
                self.fail("Practice Answer", "No questions available")
                return False
                
            # Answer the first question
            question = questions[0]
            word_id = question.get("word_id")
            mode = question.get("mode", "mcq")
            
            answer_resp = requests.post(
                f"{BASE_URL}/api/practice/answer",
                headers={"Authorization": f"Bearer {self.token}"},
                json={
                    "word_id": word_id,
                    "mode": mode,
                    "correct": True,
                    "response_time_ms": 2000
                },
                timeout=10
            )
            
            if answer_resp.status_code == 200:
                answer_data = answer_resp.json()
                xp_gain = answer_data.get("xp_gain", 0)
                status = answer_data.get("status", "")
                self.success("Practice Answer", f"XP gained: {xp_gain}, Status: {status}")
                return True
            else:
                self.fail("Practice Answer", f"Status {answer_resp.status_code}: {answer_resp.text}")
                return False
        except Exception as e:
            self.fail("Practice Answer", f"Exception: {str(e)}")
            return False
            
    def test_mission(self):
        """Test GET /api/mission - should return mission data"""
        if not self.token:
            self.fail("Mission", "No token available")
            return False
            
        try:
            resp = requests.get(
                f"{BASE_URL}/api/mission",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                total_words = data.get("total_words", 0)
                review_count = data.get("review_count", 0)
                new_count = data.get("new_count", 0)
                self.success("Mission", f"Total: {total_words}, Review: {review_count}, New: {new_count}")
                return True
            else:
                self.fail("Mission", f"Status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Mission", f"Exception: {str(e)}")
            return False
            
    def test_progress(self):
        """Test GET /api/progress - should return user progress with XP"""
        if not self.token:
            self.fail("Progress", "No token available")
            return False
            
        try:
            resp = requests.get(
                f"{BASE_URL}/api/progress",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                xp = data.get("xp", 0)
                level = data.get("level", 0)
                words_learned = data.get("words_learned", 0)
                self.success("Progress", f"XP: {xp}, Level: {level}, Words learned: {words_learned}")
                return True
            else:
                self.fail("Progress", f"Status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Progress", f"Exception: {str(e)}")
            return False
            
    def test_entitlements(self):
        """Test GET /api/entitlements - should return tier and limits"""
        if not self.token:
            self.fail("Entitlements", "No token available")
            return False
            
        try:
            resp = requests.get(
                f"{BASE_URL}/api/entitlements",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                tier = data.get("tier", "")
                limits = data.get("limits", {})
                self.success("Entitlements", f"Tier: {tier}, Limits: {limits}")
                return True
            else:
                self.fail("Entitlements", f"Status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            self.fail("Entitlements", f"Exception: {str(e)}")
            return False
            
    def test_data_source(self):
        """Verify data is coming from Supabase (not MongoDB)"""
        # Check backend .env to confirm DB_BACKEND=supabase
        try:
            with open("/app/backend/.env", "r") as f:
                env_content = f.read()
                if "DB_BACKEND=supabase" in env_content:
                    self.success("Data Source", "Backend configured with DB_BACKEND=supabase")
                    return True
                else:
                    self.fail("Data Source", "Backend not configured with DB_BACKEND=supabase")
                    return False
        except Exception as e:
            self.fail("Data Source", f"Could not verify .env: {str(e)}")
            return False
            
    def run_all_tests(self):
        """Run all tests in sequence"""
        self.log("\n" + "="*60, Colors.BLUE)
        self.log("Vocabist Backend Acceptance Tests", Colors.BLUE)
        self.log("Testing Supabase + RLS Integration", Colors.BLUE)
        self.log("="*60 + "\n", Colors.BLUE)
        
        # Run tests in order
        self.test_health()
        self.test_data_source()
        self.test_login()
        self.test_auth_me()
        self.test_words_list()
        self.test_word_detail()
        self.test_topics()
        self.test_exams()
        self.test_practice_start()
        self.test_practice_answer()
        self.test_mission()
        self.test_progress()
        self.test_entitlements()
        
        # Print summary
        self.log("\n" + "="*60, Colors.BLUE)
        self.log("TEST SUMMARY", Colors.BLUE)
        self.log("="*60, Colors.BLUE)
        self.log(f"Total Tests: {self.passed + self.failed}", Colors.BLUE)
        self.log(f"Passed: {self.passed}", Colors.GREEN)
        self.log(f"Failed: {self.failed}", Colors.RED)
        
        if self.failures:
            self.log("\nFailed Tests:", Colors.RED)
            for failure in self.failures:
                self.log(f"  - {failure['test']}: {failure['reason']}", Colors.RED)
        
        self.log("="*60 + "\n", Colors.BLUE)
        
        return self.failed == 0

if __name__ == "__main__":
    runner = TestRunner()
    success = runner.run_all_tests()
    sys.exit(0 if success else 1)
