from app.ai_client import clean_response


def test_clean_response_strips_think_block():
    raw = "<think>internal reasoning here</think>Hello!"
    assert clean_response(raw) == "Hello!"


def test_clean_response_strips_dangling_think():
    raw = "<think>truncated reasoning without close tag"
    assert clean_response(raw) == ""


def test_clean_response_keeps_normal_text():
    assert clean_response("Just an answer.") == "Just an answer."


def test_clean_response_handles_empty():
    assert clean_response("") == ""
    assert clean_response(None) == ""  # type: ignore[arg-type]


def test_clean_response_multiple_blocks():
    raw = "<think>a</think>Hi <think>b</think> there"
    assert clean_response(raw) == "Hi  there"
