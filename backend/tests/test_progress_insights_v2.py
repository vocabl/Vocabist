"""
Backend tests for Progress & Insights 2.0 (iteration 4)

Tests:
- GET /api/progress returns new fields: mastery_distribution, recently_mastered, in_progress, total_sessions
- GET /api/progress preserves all existing fields
- GET /api/review/slipping still works (regression)
"""
import pytest
import requests
import os
from datetime import datetime
from dotenv import load_dotenv

# Load frontend .env to get EXPO_PUBLIC_BACKEND_URL
load_dotenv('/app/frontend/.env')
BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', 'https://vocabist-restore.preview.emergentagent.com').rstrip('/')

@pytest.fixture(scope="module")
def test_user():
    """Register a fresh test user for progress testing"""
    payload = {
        "email": "e2e_progress@vocabist.app",
        "password": "test1234",
        "name": "E2E Tester"
    }
    # Clean up if exists (ignore errors)
    try:
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": payload["email"],
            "password": payload["password"]
        })
        if login_resp.status_code == 200:
            token = login_resp.json()["token"]
            # Delete existing session
            requests.post(f"{BASE_URL}/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    except:
        pass
    
    # Register new user
    resp = requests.post(f"{BASE_URL}/api/auth/register", json=payload)
    assert resp.status_code in (200, 409), f"Register failed: {resp.status_code} {resp.text}"
    
    if resp.status_code == 409:
        # User exists, login instead
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": payload["email"],
            "password": payload["password"]
        })
        assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    
    data = resp.json()
    assert "token" in data
    assert "user" in data
    
    return {
        "token": data["token"],
        "user_id": data["user"]["user_id"],
        "email": data["user"]["email"]
    }


class TestProgressEndpoint:
    """Test GET /api/progress with new fields"""
    
    def test_progress_returns_200(self, test_user):
        """Progress endpoint returns 200"""
        resp = requests.get(
            f"{BASE_URL}/api/progress",
            headers={"Authorization": f"Bearer {test_user['token']}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    def test_progress_has_new_mastery_distribution(self, test_user):
        """Progress returns mastery_distribution with SEEN, LEARNING, RECALLING, MASTERED"""
        resp = requests.get(
            f"{BASE_URL}/api/progress",
            headers={"Authorization": f"Bearer {test_user['token']}"}
        )
        data = resp.json()
        
        assert "mastery_distribution" in data, "Missing mastery_distribution field"
        dist = data["mastery_distribution"]
        
        # Check all required keys
        assert "SEEN" in dist, "Missing SEEN in mastery_distribution"
        assert "LEARNING" in dist, "Missing LEARNING in mastery_distribution"
        assert "RECALLING" in dist, "Missing RECALLING in mastery_distribution"
        assert "MASTERED" in dist, "Missing MASTERED in mastery_distribution"
        
        # Check types
        assert isinstance(dist["SEEN"], int), "SEEN should be int"
        assert isinstance(dist["LEARNING"], int), "LEARNING should be int"
        assert isinstance(dist["RECALLING"], int), "RECALLING should be int"
        assert isinstance(dist["MASTERED"], int), "MASTERED should be int"
        
        # Check non-negative
        assert dist["SEEN"] >= 0
        assert dist["LEARNING"] >= 0
        assert dist["RECALLING"] >= 0
        assert dist["MASTERED"] >= 0
    
    def test_progress_has_recently_mastered(self, test_user):
        """Progress returns recently_mastered array"""
        resp = requests.get(
            f"{BASE_URL}/api/progress",
            headers={"Authorization": f"Bearer {test_user['token']}"}
        )
        data = resp.json()
        
        assert "recently_mastered" in data, "Missing recently_mastered field"
        assert isinstance(data["recently_mastered"], list), "recently_mastered should be array"
        
        # For fresh user, should be empty
        # If not empty, validate structure
        if len(data["recently_mastered"]) > 0:
            item = data["recently_mastered"][0]
            assert "word_id" in item
            assert "headword" in item
            assert "mastery_score" in item
            assert "mastered_at" in item
            assert isinstance(item["mastery_score"], (int, float))
    
    def test_progress_has_in_progress(self, test_user):
        """Progress returns in_progress count"""
        resp = requests.get(
            f"{BASE_URL}/api/progress",
            headers={"Authorization": f"Bearer {test_user['token']}"}
        )
        data = resp.json()
        
        assert "in_progress" in data, "Missing in_progress field"
        assert isinstance(data["in_progress"], int), "in_progress should be int"
        assert data["in_progress"] >= 0, "in_progress should be non-negative"
    
    def test_progress_has_total_sessions(self, test_user):
        """Progress returns total_sessions count"""
        resp = requests.get(
            f"{BASE_URL}/api/progress",
            headers={"Authorization": f"Bearer {test_user['token']}"}
        )
        data = resp.json()
        
        assert "total_sessions" in data, "Missing total_sessions field"
        assert isinstance(data["total_sessions"], int), "total_sessions should be int"
        assert data["total_sessions"] >= 0, "total_sessions should be non-negative"
    
    def test_progress_preserves_existing_fields(self, test_user):
        """Progress preserves all existing fields from previous versions"""
        resp = requests.get(
            f"{BASE_URL}/api/progress",
            headers={"Authorization": f"Bearer {test_user['token']}"}
        )
        data = resp.json()
        
        # Existing fields that must be preserved
        required_fields = [
            "words_learned",
            "words_mastered",
            "accuracy",
            "streak",
            "longest_streak",
            "xp",
            "level",
            "achievements",
            "weak_areas",
            "study_minutes"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing existing field: {field}"
        
        # Validate types
        assert isinstance(data["words_learned"], int)
        assert isinstance(data["words_mastered"], int)
        assert isinstance(data["accuracy"], int)
        assert isinstance(data["streak"], int)
        assert isinstance(data["longest_streak"], int)
        assert isinstance(data["xp"], int)
        assert isinstance(data["level"], int)
        assert isinstance(data["achievements"], list)
        assert isinstance(data["weak_areas"], list)
        assert isinstance(data["study_minutes"], int)
    
    def test_progress_achievements_structure(self, test_user):
        """Achievements array has correct structure"""
        resp = requests.get(
            f"{BASE_URL}/api/progress",
            headers={"Authorization": f"Bearer {test_user['token']}"}
        )
        data = resp.json()
        
        achievements = data["achievements"]
        assert len(achievements) > 0, "Should have at least one achievement"
        
        # Check first achievement structure
        ach = achievements[0]
        assert "key" in ach
        assert "title" in ach
        assert "desc" in ach
        assert "goal" in ach
        assert "value" in ach
        assert "unlocked" in ach
        assert "progress" in ach
        
        assert isinstance(ach["unlocked"], bool)
        assert isinstance(ach["progress"], int)
        assert 0 <= ach["progress"] <= 100
    
    def test_progress_weak_areas_structure(self, test_user):
        """Weak areas array has correct structure when present"""
        resp = requests.get(
            f"{BASE_URL}/api/progress",
            headers={"Authorization": f"Bearer {test_user['token']}"}
        )
        data = resp.json()
        
        weak_areas = data["weak_areas"]
        # For fresh user, may be empty
        if len(weak_areas) > 0:
            wa = weak_areas[0]
            assert "topic" in wa
            assert "name" in wa
            assert "avg_mastery" in wa
            assert "mastered_count" in wa
            assert "total_count" in wa
            assert "mastery_percent" in wa


class TestReviewSlippingRegression:
    """Regression test: GET /api/review/slipping still works"""
    
    def test_slipping_returns_200(self, test_user):
        """Slipping endpoint returns 200"""
        resp = requests.get(
            f"{BASE_URL}/api/review/slipping",
            headers={"Authorization": f"Bearer {test_user['token']}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    def test_slipping_has_correct_structure(self, test_user):
        """Slipping endpoint returns count and words array"""
        resp = requests.get(
            f"{BASE_URL}/api/review/slipping",
            headers={"Authorization": f"Bearer {test_user['token']}"}
        )
        data = resp.json()
        
        assert "count" in data, "Missing count field"
        assert "words" in data, "Missing words field"
        assert isinstance(data["count"], int)
        assert isinstance(data["words"], list)
        assert data["count"] == len(data["words"]), "count should match words array length"


class TestProgressWithActivity:
    """Test progress endpoint after some activity"""
    
    def test_progress_after_practice_session(self, test_user):
        """Progress updates after completing a practice session"""
        # Start a practice session
        start_resp = requests.post(
            f"{BASE_URL}/api/practice/start?source=mission",
            headers={"Authorization": f"Bearer {test_user['token']}"}
        )
        assert start_resp.status_code == 200
        questions = start_resp.json().get("questions", [])
        
        if len(questions) > 0:
            # Answer one question correctly
            word_id = questions[0]["word_id"]
            answer_resp = requests.post(
                f"{BASE_URL}/api/practice/answer",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={
                    "word_id": word_id,
                    "mode": "multiple_choice",
                    "correct": True,
                    "response_time_ms": 3000
                }
            )
            assert answer_resp.status_code == 200
            
            # Complete session
            complete_resp = requests.post(
                f"{BASE_URL}/api/practice/complete",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={
                    "answered": 1,
                    "correct": 1,
                    "duration_ms": 5000,
                    "source": "mission"
                }
            )
            assert complete_resp.status_code == 200
            
            # Check progress
            progress_resp = requests.get(
                f"{BASE_URL}/api/progress",
                headers={"Authorization": f"Bearer {test_user['token']}"}
            )
            data = progress_resp.json()
            
            # Should have at least 1 session now
            assert data["total_sessions"] >= 1, "Should have at least 1 session after completing practice"
            
            # Should have some XP
            assert data["xp"] > 0, "Should have XP after answering correctly"
            
            # Should have words in progress
            assert data["in_progress"] >= 1, "Should have at least 1 word in progress"
            
            # Mastery distribution should have at least one word
            dist = data["mastery_distribution"]
            total_words = dist["SEEN"] + dist["LEARNING"] + dist["RECALLING"] + dist["MASTERED"]
            assert total_words >= 1, "Should have at least 1 word in mastery distribution"


class TestProgressDataConsistency:
    """Test data consistency in progress response"""
    
    def test_in_progress_matches_distribution(self, test_user):
        """in_progress should match sum of SEEN + LEARNING + RECALLING"""
        resp = requests.get(
            f"{BASE_URL}/api/progress",
            headers={"Authorization": f"Bearer {test_user['token']}"}
        )
        data = resp.json()
        
        dist = data["mastery_distribution"]
        expected_in_progress = dist["SEEN"] + dist["LEARNING"] + dist["RECALLING"]
        
        assert data["in_progress"] == expected_in_progress, \
            f"in_progress ({data['in_progress']}) should equal SEEN+LEARNING+RECALLING ({expected_in_progress})"
    
    def test_words_learned_includes_mastered(self, test_user):
        """words_learned should include mastered words"""
        resp = requests.get(
            f"{BASE_URL}/api/progress",
            headers={"Authorization": f"Bearer {test_user['token']}"}
        )
        data = resp.json()
        
        # words_learned = LEARNING + RECALLING + MASTERED (excludes SEEN)
        # This is based on the backend implementation
        assert data["words_learned"] >= data["words_mastered"], \
            "words_learned should be >= words_mastered"
