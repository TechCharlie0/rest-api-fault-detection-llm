
import requests

def test_post_user():

    url = "https://petstore.swagger.io/v2/user"

    payload = {'id': 1, 'username': 'sample', 'firstName': 'sample', 'lastName': 'sample', 'email': 'sample', 'password': 'sample', 'phone': 'sample', 'userStatus': 1}

    response = requests.request(
        "POST",
        url,
        json=payload
    )

    assert response.status_code < 500
