
import requests

def test_put_user_username():

    url = "https://petstore.swagger.io/v2/user/testuser"

    payload = {'id': 1, 'username': 'sample', 'firstName': 'sample', 'lastName': 'sample', 'email': 'sample', 'password': 'sample', 'phone': 'sample', 'userStatus': 1}

    response = requests.request(
        "PUT",
        url,
        json=payload
    )

    assert response.status_code < 500
