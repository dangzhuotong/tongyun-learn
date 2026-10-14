from tongyun_learn.errors import ApiError


def test_api_error_attributes():
    err = ApiError(
        status=404,
        code="not_found",
        message="资源不存在",
        details={"id": 123},
        headers={"Retry-After": "60"},
    )
    assert err.status == 404
    assert err.status_code == 404
    assert err.code == "not_found"
    assert err.message == "资源不存在"
    assert str(err) == "资源不存在"
    assert err.details == {"id": 123}
    assert err.headers == {"Retry-After": "60"}


def test_api_error_to_dict_with_details():
    err = ApiError(422, "validation_error", "参数错误", details=["field required"])
    d = err.to_dict()
    assert d == {
        "error": {
            "code": "validation_error",
            "message": "参数错误",
            "details": ["field required"],
        }
    }


def test_api_error_to_dict_without_details():
    err = ApiError(401, "unauthorized", "缺少令牌")
    d = err.to_dict()
    assert d == {
        "error": {
            "code": "unauthorized",
            "message": "缺少令牌",
        }
    }
