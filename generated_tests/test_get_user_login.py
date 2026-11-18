
import requests

def test_get_user_login():

    url = "https://petstore.swagger.io/v2/user/login"

    response = requests.request(
        "GET",
        url
    )

    assert response.status_code < 500
