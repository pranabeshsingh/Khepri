import pytest
from unittest.mock import patch, MagicMock
from pithon.agent.search import should_search, search_duckduckgo, format_search_context, clean_html_text

def test_should_search_heuristic():
    assert should_search("what is the latest news about python?") is True
    assert should_search("today weather forecast in Kolkata") is True
    assert should_search("who is the current president?") is True
    assert should_search("what is happening with linux kernel?") is True
    assert should_search("hello, how are you?") is False
    assert should_search("explain quicksort algorithm") is False

def test_clean_html_text():
    raw = "<b>Python</b> 3.12 is <i>released</i>! &amp; &quot;awesome&quot;"
    cleaned = clean_html_text(raw)
    assert cleaned == 'Python 3.12 is released! & "awesome"'

def test_format_search_context():
    results = [
        {"title": "Example Title", "snippet": "Example snippet about stuff.", "url": "https://example.com/1"},
        {"title": "Second Title", "snippet": "Another snippet.", "url": "https://example.com/2"}
    ]
    formatted = format_search_context(results, "example query")
    assert '[Live Web Search Results for: "example query"]' in formatted
    assert "1. Title: Example Title" in formatted
    assert "URL: https://example.com/1" in formatted
    assert "2. Title: Second Title" in formatted

@patch("urllib.request.urlopen")
def test_search_duckduckgo_mock(mock_urlopen):
    # Mock DuckDuckGo HTML response
    sample_html = """
    <div class="result results_links results_links_deep web-result ">
      <h2 class="result__title">
        <a class="result__url" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fnews">Example News</a>
      </h2>
      <a class="result__snippet">Breaking news snippet for testing.</a>
    </div>
    """
    mock_resp = MagicMock()
    mock_resp.read.return_value = sample_html.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    results = search_duckduckgo("test query", max_results=1)
    assert len(results) == 1
    assert results[0]["title"] == "Example News"
    assert "Breaking news snippet" in results[0]["snippet"]
    assert "https://example.com/news" in results[0]["url"]
