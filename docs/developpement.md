# Python Test Writing Guidelines

## Purpose

This document defines the conventions and best practices for writing Python tests in the `SIPMediaGW` project, especially for `pytest`-based API and unit tests.

---

## 1. Project structure

- Place test files under:
  - `test/api/` for FastAPI and gateway API tests
  - `test/proxy/` for proxy-related tests
- Keep production code and test code separate
- Use `docs/` for documentation and style guides

---

## 2. Test file structure

- Prefer grouping related tests in classes:
  - `class TestSomething:`
- Keep each test focused and atomic:
  - one use case per test
  - one main assertion intent per test
- Use consistent section headers, e.g. `# -----------------------`

---

## 3. Test naming

Use descriptive names:

- `test_<action>_<condition>_<expected_result>`
- Examples:
  - `test_start_gateway_success`
  - `test_stop_gateway_not_found`
  - `test_get_status_returns_up_when_running`

---

## 4. Fixtures

- Use `pytest` fixtures for shared setup
- Common fixtures:
  - `client`
  - `mock_docker_gateway`
  - `override_backend`
  - `redis_mock`
- Example:

```python
@pytest.fixture
def client():
    return TestClient(app)
```

---

## 5. Mocking and patching

- Use `Mock(spec=...)` to enforce interface expectations
- Choose one style consistently:
  - decorator style: `@patch(...)`
  - context manager style: `with patch(...)`
- Avoid mixing both styles in the same file unless there is a strong reason

---

## 6. Assertions

- Prefer explicit assertions
- Avoid debugging `print()` statements
- Check HTTP status code before parsing JSON:

```python
assert response.status_code == 200
data = response.json()
```

- For exceptions:

```python
with pytest.raises(ValueError, match="..."):
    ...
```

---

## 7. FastAPI route tests

- Use `TestClient(app)` via fixture
- Validate:
  - HTTP status code
  - JSON response body
- Example:

```python
response = client.post("/gateway/start", json={...})
assert response.status_code == 200
assert response.json()["status"] == "success"
```

---

## 8. Unit tests

- Test functions and methods in isolation
- Mock external dependencies:
  - `subprocess.Popen`
  - file access
  - Redis
  - HTTP clients
- Ensure tests are fast and deterministic

---

## 9. Readability

- Use docstrings or clear test names
- Example:

```python
def test_start_gateway_success(self, client, override_backend):
    """Should return 200 and gateway data."""
    ...
```

- Choose either docstrings or descriptive test names consistently

---

## 10. Specific style recommendations

- Use `assert result == expected` not `assert result is expected`
- Stick with `pytest` only
- Keep test files self-contained and easy to read
- Avoid large, multi-purpose tests

---

## 11. Recommended placement

- Primary file: `docs/developpement.md`
- Alternative or supplement:
  - `docs/testing.md`
  - `test/README.md`
