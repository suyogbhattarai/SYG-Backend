# test_celery.py
import requests
import time

# Upload a test version
response = requests.post(
    'http://127.0.0.1:8000/versioning/upload_version/',
    json={
        'project_name': 'TestProject',
        'commit_message': 'Test version',
        'file_list': []
    }
)

if response.status_code == 201:
    push_id = response.json()['push_id']
    print(f"Push created: {push_id}")
    
    # Poll status
    for i in range(10):
        time.sleep(2)
        status_response = requests.get(
            f'http://127.0.0.1:8000/versioning/push_status/{push_id}/'
        )
        data = status_response.json()
        print(f"Progress: {data['progress']}% - {data['status']} - {data['message']}")
        
        if data['status'] in ['done', 'failed']:
            break
else:
    print(f"Error: {response.status_code} - {response.text}")