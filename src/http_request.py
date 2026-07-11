"""
Event Retrieval API Client - AIC25 Competition
This file implements the API workflow for submitting video search results
"""

import requests
import json


class EventRetrievalClient:
    """Client for interacting with the Event Retrieval API"""
    
    BASE_URL = "https://eventretrieval.oj.io.vn/api/v2"
    
    def __init__(self, username, password):
        """
        Initialize the client with credentials
        
        Args:
            username (str): Your username
            password (str): Your password
        """
        self.username = username
        self.password = password
        self.session_id = None
        self.user_id = None
        self.evaluation_id = None
    
    def login(self):
        """
        Step 1: Login to get session ID
        
        Returns:
            dict: Login response containing id, username, role, sessionId
        """
        url = f"{self.BASE_URL}/login"
        body = {
            "username": self.username,
            "password": self.password
        }
        
        try:
            print("=== Step 1: Logging in ===")
            response = requests.post(url, json=body)
            response.raise_for_status()
            
            data = response.json()
            self.session_id = data.get("sessionId")
            self.user_id = data.get("id")
            
            print(f"Login successful!")
            print(f"User ID: {self.user_id}")
            print(f"Username: {data.get('username')}")
            print(f"Role: {data.get('role')}")
            print(f"Session ID: {self.session_id}\n")
            
            return data
        except requests.exceptions.RequestException as e:
            print(f"Login failed: {e}")
            return None
    
    def get_evaluation_list(self):
        """
        Step 2: Get evaluation ID
        
        Returns:
            list: List of evaluations with id, name, type, status
        """
        if not self.session_id:
            print("Error: Not logged in. Please call login() first.")
            return None
        
        url = f"{self.BASE_URL}/client/evaluation/list"
        params = {
            "session": self.session_id
        }
        
        try:
            print("=== Step 2: Getting evaluation list ===")
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data and len(data) > 0:
                # Get the first active evaluation
                for evaluation in data:
                    if evaluation.get("status") == "ACTIVE":
                        self.evaluation_id = evaluation.get("id")
                        print(f"Found active evaluation:")
                        print(f"Evaluation ID: {self.evaluation_id}")
                        print(f"Name: {evaluation.get('name')}")
                        print(f"Type: {evaluation.get('type')}")
                        print(f"Status: {evaluation.get('status')}\n")
                        break
            
            return data
        except requests.exceptions.RequestException as e:
            print(f"Failed to get evaluation list: {e}")
            return None
    
    def submit_kis_answer(self, video_id, start_time_ms, end_time_ms):
        """
        Step 3: Submit KIS (Keyframe Instance Search) answer
        
        Args:
            video_id (str): Video ID (filename without extension)
            start_time_ms (int): Start time in milliseconds
            end_time_ms (int): End time in milliseconds
        
        Returns:
            dict: Submission response
        """
        body = {
            "answerSets": [{
                "answers": [{
                    "mediaItemName": video_id,
                    "start": start_time_ms,
                    "end": end_time_ms
                }]
            }]
        }
        
        return self._submit(body, "KIS")
    
    def submit_qa_answer(self, answer, video_id, time_ms):
        """
        Step 3: Submit QA (Question Answering) answer
        
        Args:
            answer (str): The answer text
            video_id (str): Video ID (filename without extension)
            time_ms (int): Time in milliseconds
        
        Returns:
            dict: Submission response
        """
        body = {
            "answerSets": [{
                "answers": [{
                    "text": f"QA-{answer}-{video_id}-{time_ms}"
                }]
            }]
        }
        
        return self._submit(body, "QA")
    
    def submit_trake_answer(self, video_id, frame_ids_str):
        """
        Step 3: Submit TRAKE (Temporal Ranking) answer
        
        Args:
            video_id (str): Video ID (filename without extension)
            frame_ids_str (str): Comma-separated string of frame IDs
        
        Returns:
            dict: Submission response
        """
        body = {
            "answerSets": [{
                "answers": [{
                    "text": f"TR-{video_id}-{frame_ids_str}"
                }]
            }]
        }
        
        return self._submit(body, "TRAKE")
    
    def _submit(self, body, submission_type):
        """
        Internal method to submit answers
        
        Args:
            body (dict): The submission body
            submission_type (str): Type of submission (KIS, QA, TRAKE)
        
        Returns:
            dict: Submission response
        """
        if not self.session_id:
            print("Error: Not logged in. Please call login() first.")
            return None
        
        if not self.evaluation_id:
            print("Error: No evaluation ID. Please call get_evaluation_list() first.")
            return None
        
        url = f"{self.BASE_URL}/submit/{self.evaluation_id}"
        params = {
            "session": self.session_id
        }
        
        try:
            print(f"=== Step 3: Submitting {submission_type} answer ===")
            print(f"Submission body: {json.dumps(body, indent=2)}")
            
            response = requests.post(url, params=params, json=body)
            response.raise_for_status()
            
            data = response.json()
            print(f"Submission successful!")
            print(f"Response: {json.dumps(data, indent=2)}\n")
            
            return data
        except requests.exceptions.RequestException as e:
            print(f"Submission failed: {e}")
            if hasattr(e.response, 'text'):
                print(f"Error details: {e.response.text}")
            return None


# Example usage functions
def example_workflow():
    """Example of complete workflow: login -> get evaluation -> submit"""
    # Replace with your actual credentials
    USERNAME = "team018"
    PASSWORD = "u9K98nA67Q"
    
    # Initialize client
    client = EventRetrievalClient(USERNAME, PASSWORD)
    
    # Step 1: Login
    login_response = client.login()
    if not login_response:
        print("Login failed, exiting...")
        return
    
    # Step 2: Get evaluation list
    evaluations = client.get_evaluation_list()
    if not evaluations:
        print("Failed to get evaluations, exiting...")
        return
    
    # Step 3: Submit answers (examples)
    
    # # Example 1: Submit KIS answer
    # client.submit_kis_answer(
    #     video_id="K03_V019",
    #     start_time_ms=390766,
    #     end_time_ms=390766
    # )
    
    # # Example 2: Submit QA answer
    # client.submit_qa_answer(
    #     answer="person wearing red shirt",
    #     video_id="L01_V002",
    #     time_ms=12000
    # )
    
    # # Example 3: Submit TRAKE answer
    client.submit_trake_answer(
        video_id="K07_V025",
        frame_ids_str="22200,22260,22350"
    )


if __name__ == "__main__":
    # print("Event Retrieval API Client\n")
    # print("=" * 50)
    # print("\nTo use this client:")
    # print("1. Replace <username> and <password> with your credentials")
    # print("2. Run example_workflow() or create your own workflow")
    # print("3. Make sure you don't submit duplicate results for the same query")
    # print("\n" + "=" * 50 + "\n")
    
    # Uncomment to run the example workflow
    example_workflow()